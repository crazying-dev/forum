"use client";

import { Fragment, useMemo, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Comment } from "@/lib/api";
import { timeAgo } from "@/lib/constants";
import { UserAvatar, UserName } from "./ui/UserAvatar";
import { UserGuildChip } from "./ui/UserGuildChip";
import Markdown from "./Markdown";

// 表情包面板（当前仅 emoji 字符，按分类切换）
const EMOJI_CATEGORIES: { name: string; icon: string; emojis: string[] }[] = [
  {
    name: "表情",
    icon: "😀",
    emojis: ["😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😘", "😎", "🤔", "😅", "😉", "🙃", "😭", "😢", "😡", "🤬", "😤", "😳", "🥺", "😴", "🤯", "😇", "🙄"],
  },
  {
    name: "手势",
    icon: "👍",
    emojis: ["👍", "👎", "👏", "🙏", "💪", "🤝", "✌️", "🤞", "👌", "👊", "🖐️", "🙌", "🤙", "👋", "💅", "🫶"],
  },
  {
    name: "爱心",
    icon: "❤️",
    emojis: ["❤️", "💔", "💕", "💖", "💘", "💝", "💯", "✨", "🔥", "⭐", "🌟", "💫", "⚡", "💥", "💤", "💦"],
  },
  {
    name: "食物",
    icon: "🍕",
    emojis: ["🍎", "🍌", "🍉", "🍇", "🍓", "🍔", "🍕", "🍟", "🌭", "🍜", "🍣", "🍰", "🍦", "☕", "🍺", "🥤"],
  },
  {
    name: "动物",
    icon: "🐱",
    emojis: ["🐱", "🐶", "🐼", "🐰", "🦊", "🐸", "🐷", "🐵", "🐯", "🦁", "🐦", "🐧", "🌹", "🌸", "🌵", "🌈"],
  },
  {
    name: "活动",
    icon: "🎉",
    emojis: ["🎉", "🎊", "🎈", "🎁", "🏆", "🚀", "🎮", "🎯", "🎨", "🎤", "🎧", "⚽", "🏀", "🏸", "🎳", "🎲"],
  },
];

/** 单条评论（与 legacy renderComment 结构 1:1，支持点赞/回复标识/删除/回复按钮） */
function CommentItem({
  c,
  parentChain,
  isReply = false,
  canDelete,
  userId,
  onReply,
  onDelete,
  onLike,
}: {
  c: Comment;
  // 「根 → … → 直接父评论」完整链（root 在前）；缺失时不渲染“回复 xxx”行
  parentChain?: Comment[];
  isReply?: boolean;
  canDelete: boolean;
  userId: string | null;
  onReply: (c: Comment) => void;
  onDelete: (id: string) => void;
  onLike: (c: Comment) => void;
}) {
  return (
    <div className={`comment-item ${isReply ? "comment-item-reply" : ""}`} data-comment-id={c.id}>
      <Link href={`/users/${c.user_id}`} className="comment-avatar">
        <UserAvatar src={c.user_avatar} userId={c.user_id} />
      </Link>
      <div className="comment-body">
        <div className="comment-header">
          <Link href={`/users/${c.user_id}`} className="comment-author Username">
            <UserName name={c.user_name} />
          </Link>
          <UserGuildChip name={c.user_guild_name} color={c.user_guild_theme_color} isLeader={c.user_is_leader} />
          <span className="comment-time">{timeAgo(c.created_at)}</span>
        </div>
        {parentChain && parentChain.length > 0 && (
          <div className="comment-reply-to">
            回复{" "}
            {parentChain.map((u, i) => (
              <Fragment key={u.id}>
                {i > 0 && " → "}
                <Link href={`/users/${u.user_id}`} className="Username">
                  <UserName name={u.user_name} />
                </Link>
                {/* 仅最后一段（直接父评论）后跟会馆身份 chip，中间祖先不加 */}
                {i === parentChain.length - 1 && (
                  <UserGuildChip name={u.user_guild_name} color={u.user_guild_theme_color} isLeader={u.user_is_leader} />
                )}
              </Fragment>
            ))}
          </div>
        )}
        <div className="comment-text">
          <Markdown content={c.content} />
        </div>
        <div className="comment-footer">
          <button
            className={`comment-like comment-like-btn ${c.liked_by_me ? "liked" : ""}`}
            title="点赞"
            onClick={() => onLike(c)}
          >
            <i className={`fa ${c.liked_by_me ? "fa-thumbs-up" : "fa-thumbs-o-up"}`}></i> {c.likes || 0}
          </button>
          <button className="comment-reply-btn" data-comment-id={c.id} data-user-name={c.user_name} onClick={() => onReply(c)}>
            <i className="fa fa-reply"></i> 回复
          </button>
          {canDelete && (
            <button className="comment-delete-btn" title="删除" onClick={() => onDelete(c.id)}>
              <i className="fa fa-trash-o"></i>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** 默认展开深度：depth < 2 的节点默认展开（即默认可见第 0/1/2 三层），更深层级默认折叠 */
const DEFAULT_EXPANDED_DEPTH = 2;

/** 深度上限：递归渲染深度达到 50 即停止（防环双保险之一） */
const MAX_DEPTH = 50;

/** 模块级空祖先集：顶层节点无祖先（节点内会复制后再加入自身，不修改此常量） */
const EMPTY_ANCESTORS: Set<string> = new Set();

/**
 * 从 parentMap 沿 parent_id 向上回溯，返回「根 → c（含 c）」的祖先链（root 在前）。
 * 遇到缺失父级或成环时链在此截断（可能非完整链），最多回溯 MAX_DEPTH 层。
 */
function ancestorChain(c: Comment, parentMap: Record<string, Comment>): Comment[] {
  const chain: Comment[] = [c];
  const seen = new Set<string>([c.id]);
  let cur = c;
  let guard = 0;
  while (cur.parent_id && guard < MAX_DEPTH) {
    const parent = parentMap[cur.parent_id];
    if (!parent || seen.has(parent.id)) break;
    chain.unshift(parent);
    seen.add(parent.id);
    cur = parent;
    guard++;
  }
  return chain;
}

/**
 * 递归评论节点：按 childrenMap 以 parent_id 真·无限层级嵌套渲染。
 * - 默认只展开前几级（DEFAULT_EXPANDED_DEPTH），由 CommentSection 的 expanded 状态覆盖；
 * - 锚点（#comment-xxx，且目标存在）作为「默认展开」的补充；用户的收起/展开操作优先；
 * - ancestors 集合 + MAX_DEPTH 深度上限双保险，防止异常数据成环导致无限递归。
 */
function CommentNode({
  c,
  depth,
  ancestors,
  childrenMap,
  parentMap,
  userId,
  expanded,
  onToggle,
  anchorDefaultExpand,
  onReply,
  onDelete,
  onLike,
}: {
  c: Comment;
  depth: number;
  ancestors: Set<string>;
  childrenMap: Record<string, Comment[]>;
  parentMap: Record<string, Comment>;
  userId: string | null;
  expanded: Record<string, boolean>;
  onToggle: (id: string, nextShown: boolean) => void;
  anchorDefaultExpand: boolean;
  onReply: (c: Comment) => void;
  onDelete: (id: string) => void;
  onLike: (c: Comment) => void;
}) {
  // 超出深度上限：停止继续渲染（防环双保险之二）
  if (depth >= MAX_DEPTH) return null;

  const nextAncestors = new Set(ancestors);
  nextAncestors.add(c.id);
  const nextDepth = depth + 1;
  // 过滤已在祖先链上的节点（防环）+ 超过深度上限的后代
  const children =
    nextDepth >= MAX_DEPTH ? [] : (childrenMap[c.id] || []).filter((child) => !nextAncestors.has(child.id));
  const hasChildren = children.length > 0;
  // 显示判断：用户操作覆盖 > 默认值（默认展开前几级；锚点目标存在时默认全展开）
  const shown = expanded[c.id] ?? (anchorDefaultExpand || depth < DEFAULT_EXPANDED_DEPTH);
  // 直接父评论（孤儿子评论父级缺失时为 undefined，“回复 xxx”行不渲染）
  const parent = c.parent_id ? parentMap[c.parent_id] : undefined;
  const parentChain = parent ? ancestorChain(parent, parentMap) : undefined;

  return (
    <div>
      <CommentItem
        c={c}
        parentChain={parentChain}
        isReply={depth > 0}
        canDelete={!!userId && userId === c.user_id}
        userId={userId}
        onReply={onReply}
        onDelete={onDelete}
        onLike={onLike}
      />
      {hasChildren && (
        <>
          <button className="comment-replies-toggle" onClick={() => onToggle(c.id, !shown)}>
            <i className={`fa ${shown ? "fa-chevron-up" : "fa-chevron-down"}`}></i>{" "}
            {shown ? "收起回复" : `展开${children.length}条回复`}
          </button>
          <div className="comment-children" style={{ display: shown ? "block" : "none" }}>
            {children.map((child) => (
              <CommentNode
                key={child.id}
                c={child}
                depth={nextDepth}
                ancestors={nextAncestors}
                childrenMap={childrenMap}
                parentMap={parentMap}
                userId={userId}
                expanded={expanded}
                onToggle={onToggle}
                anchorDefaultExpand={anchorDefaultExpand}
                onReply={onReply}
                onDelete={onDelete}
                onLike={onLike}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * 评论区：根评论最新在前；子评论按 parent_id 递归嵌套（真·无限层级），
 * 默认只展开前几级，更深层级折叠；锚点跳转（#comment-xxx）时强制全部展开。
 */
export default function CommentSection({
  comments,
  userId,
  inputRef,
  replyTo,
  setReplyTo,
  onChangeReplyText,
  onSubmit,
  onDelete,
  onLike,
}: {
  comments: Comment[];
  userId: string | null;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  // path：从根到被回复评论（含自身）的完整 user_name 链，用于展示回复路径
  replyTo: { id: string; name: string; path: string[] } | null;
  setReplyTo: (v: { id: string; name: string; path: string[] } | null) => void;
  onChangeReplyText: (text: string) => void;
  onSubmit: () => void;
  onDelete: (id: string) => void;
  onLike: (c: Comment) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showEmoji, setShowEmoji] = useState(false);
  const [emojiCat, setEmojiCat] = useState(0);
  const emojiWrapRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭 emoji 面板
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (emojiWrapRef.current && !emojiWrapRef.current.contains(e.target as Node)) {
        setShowEmoji(false);
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const insertEmoji = (emoji: string) => {
    const el = inputRef.current;
    if (!el) {
      onChangeReplyText(emoji);
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? start;
    const next = el.value.slice(0, start) + emoji + el.value.slice(end);
    el.value = next;
    onChangeReplyText(next);
    const pos = start + emoji.length;
    el.focus();
    el.setSelectionRange(pos, pos);
  };

  // 锚点（#comment-xxx）：仅当目标评论真实存在时，作为「默认展开」的补充（不再强制覆盖用户折叠）
  const anchorCommentId =
    typeof window !== "undefined" && window.location.hash.startsWith("#comment-")
      ? window.location.hash.slice("#comment-".length)
      : null;

  const { mainComments, childrenMap, parentMap } = useMemo(() => {
    const parentMap: Record<string, Comment> = {};
    comments.forEach((c) => {
      parentMap[c.id] = c;
    });
    // 子评论按 parent_id 分组，组内按创建时间升序（先评先显示）；
    // 孤儿子评论（parent_id 指向的评论不在数组内）挂不到任何可见节点上，保持不渲染
    const childrenMap: Record<string, Comment[]> = {};
    comments.forEach((c) => {
      if (!c.parent_id) return;
      if (!childrenMap[c.parent_id]) childrenMap[c.parent_id] = [];
      childrenMap[c.parent_id].push(c);
    });
    Object.keys(childrenMap).forEach((pid) => {
      childrenMap[pid].sort((a, b) => new Date(a.created_at || "").getTime() - new Date(b.created_at || "").getTime());
    });
    // 顶层评论保持原有 .reverse()（最新在前，不变）
    return { mainComments: comments.filter((c) => !c.parent_id).reverse(), childrenMap, parentMap };
  }, [comments]);

  const anchorDefaultExpand = !!anchorCommentId && !!parentMap[anchorCommentId];

  const toggleReplies = (id: string, nextShown: boolean) => {
    setExpanded((p) => ({ ...p, [id]: nextShown }));
  };

  const startingReply = (c: Comment) => {
    // 点击「回复」时展开该节点：确保发送成功后的新回复立即可见（父节点可能默认折叠/被用户收起）
    setExpanded((p) => ({ ...p, [c.id]: true }));
    // 回复路径：从根到被回复评论（含自身）的完整 user_name 链
    const path = ancestorChain(c, parentMap).map((x) => x.user_name || "匿名");
    setReplyTo({ id: c.id, name: c.user_name || "匿名", path });
    onChangeReplyText(`@${c.user_name} `);
    inputRef.current?.focus();
  };

  return (
    <>
      <div className="comment-section-title">评论区</div>
      <div className="comment-input-bar">
        {replyTo && (
          <div className="comment-reply-indicator">
            <span>
              回复{" "}
              {replyTo.path.map((name, i) => (
                <Fragment key={`${i}-${name}`}>
                  {i > 0 && " → "}
                  <b className="Username">{name}</b>
                </Fragment>
              ))}
            </span>
            <button onClick={() => setReplyTo(null)}><i className="fa fa-times"></i></button>
          </div>
        )}
        <textarea
          ref={inputRef}
          id="comment-input"
          className="comment-input-textarea"
          rows={3}
          placeholder={replyTo ? `回复 ${replyTo.name}...` : "写下你的评论..."}
          maxLength={500}
          onChange={(e) => onChangeReplyText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <div className="comment-input-actions">
          <div className="comment-emoji-wrap" ref={emojiWrapRef}>
            <button
              type="button"
              className={`comment-emoji-btn ${showEmoji ? "active" : ""}`}
              onClick={() => setShowEmoji((v) => !v)}
              title="表情"
            >
              <i className="fa fa-smile-o"></i>
            </button>
            {showEmoji && (
              <div className="comment-emoji-panel">
                <div className="comment-emoji-grid">
                  {EMOJI_CATEGORIES[emojiCat].emojis.map((e) => (
                    <button type="button" className="comment-emoji-item" key={e} onClick={() => insertEmoji(e)}>
                      {e}
                    </button>
                  ))}
                </div>
                <div className="comment-emoji-tabs">
                  {EMOJI_CATEGORIES.map((c, i) => (
                    <button
                      type="button"
                      className={`comment-emoji-tab ${i === emojiCat ? "active" : ""}`}
                      key={c.name}
                      onClick={() => setEmojiCat(i)}
                      title={c.name}
                    >
                      <span className="comment-emoji-tab-icon">{c.icon}</span>
                      <span className="comment-emoji-tab-label">{c.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <button className="comment-send-btn" onClick={onSubmit}>发送</button>
        </div>
      </div>
      <div className="comment-list" id="comment-list">
        {comments.length === 0 ? (
          <div className="comment-empty">暂无评论，快来抢沙发~</div>
        ) : (
          mainComments.map((c) => (
            <CommentNode
              key={c.id}
              c={c}
              depth={0}
              ancestors={EMPTY_ANCESTORS}
              childrenMap={childrenMap}
              parentMap={parentMap}
              userId={userId}
              expanded={expanded}
              onToggle={toggleReplies}
              anchorDefaultExpand={anchorDefaultExpand}
              onReply={startingReply}
              onDelete={onDelete}
              onLike={onLike}
            />
          ))
        )}
      </div>
    </>
  );
}
