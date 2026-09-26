"use client";

import { useMemo, useEffect, useRef, useState } from "react";
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
  parent,
  isReply = false,
  canDelete,
  userId,
  onReply,
  onDelete,
  onLike,
}: {
  c: Comment;
  parent?: Comment | null;
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
        {parent && (
          <div className="comment-reply-to">
            回复{" "}
            <Link href={`/users/${parent.user_id}`} className="Username">
              <UserName name={parent.user_name} />
            </Link>
            <UserGuildChip name={parent.user_guild_name} color={parent.user_guild_theme_color} isLeader={parent.user_is_leader} />
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

/**
 * 评论区（与 legacy renderPostDetail 评论部分 1:1）：
 * 根评论（无 parent）+ 回复分组（多层归并到根），默认展示最近2条，其余折叠。
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
  replyTo: { id: string; name: string } | null;
  setReplyTo: (v: { id: string; name: string } | null) => void;
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

  // 带锚点跳转（#comment-xxx）时默认展开全部折叠回复，保证目标评论可见
  const isAnchorScroll = typeof window !== "undefined" && window.location.hash.startsWith("#comment-");

  const { mainComments, replyMap, parentMap } = useMemo(() => {
    const parentMap: Record<string, Comment> = {};
    comments.forEach((c) => {
      parentMap[c.id] = c;
    });
    const replyMap: Record<string, Comment[]> = {};
    comments.forEach((c) => {
      if (!c.parent_id) return;
      let rootId = c.parent_id;
      let visited = 0;
      while (parentMap[rootId] && parentMap[rootId].parent_id && visited < 50) {
        rootId = parentMap[rootId].parent_id!;
        visited++;
      }
      if (!replyMap[rootId]) replyMap[rootId] = [];
      replyMap[rootId].push(c);
    });
    Object.keys(replyMap).forEach((rootId) => {
      replyMap[rootId].sort((a, b) => new Date(a.created_at || "").getTime() - new Date(b.created_at || "").getTime());
    });
    return { mainComments: comments.filter((c) => !c.parent_id).reverse(), replyMap, parentMap };
  }, [comments]);

  const startingReply = (c: Comment) => {
    setReplyTo({ id: c.id, name: c.user_name || "匿名" });
    onChangeReplyText(`@${c.user_name} `);
    inputRef.current?.focus();
  };

  return (
    <>
      <div className="comment-section-title">评论区</div>
      <div className="comment-input-bar">
        {replyTo && (
          <div className="comment-reply-indicator">
            <span>回复 <b className="Username">{replyTo.name}</b></span>
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
        ) : mainComments.map((c) => {
          const replies = replyMap[c.id] || [];
          const total = replies.length;
          const visibleCount = Math.min(total, 2);
          const visibleReplies = replies.slice(total - visibleCount, total);
          const hiddenReplies = replies.slice(0, total - visibleCount);
          return (
            <div key={c.id}>
              <CommentItem
                c={c}
                canDelete={!!userId && userId === c.user_id}
                userId={userId}
                onReply={startingReply}
                onDelete={onDelete}
                onLike={onLike}
              />
              {replies.length > 0 && (
                <div className="comment-replies">
                  {visibleReplies.map((r) => (
                    <CommentItem
                      key={r.id}
                      c={r}
                      parent={parentMap[r.parent_id!]}
                      isReply
                      canDelete={!!userId && userId === r.user_id}
                      userId={userId}
                      onReply={startingReply}
                      onDelete={onDelete}
                      onLike={onLike}
                    />
                  ))}
                  {hiddenReplies.length > 0 && (
                    <>
                      <button className="comment-replies-toggle" data-parent-id={c.id} onClick={() => setExpanded((p) => ({ ...p, [c.id]: !p[c.id] }))}>
                        <i className="fa fa-chevron-down"></i> 展开{hiddenReplies.length}条回复
                      </button>
                      <div className={`comment-replies-hidden ${expanded[c.id] ? "" : ""}`} data-parent-id={c.id} style={{ display: expanded[c.id] || isAnchorScroll ? "block" : "none" }}>
                        {hiddenReplies.map((r) => (
                          <CommentItem
                            key={r.id}
                            c={r}
                            parent={parentMap[r.parent_id!]}
                            isReply
                            canDelete={!!userId && userId === r.user_id}
                            userId={userId}
                            onReply={startingReply}
                            onDelete={onDelete}
                            onLike={onLike}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
