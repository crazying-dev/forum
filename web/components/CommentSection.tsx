"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Comment } from "@/lib/api";
import { timeAgo } from "@/lib/constants";
import { UserAvatar, UserName } from "./ui/UserAvatar";
import { UserGuildChip } from "./ui/UserGuildChip";
import Markdown from "./Markdown";
import RichContent from "./ui/RichContent";
import CommentEditor, { CommentEditorHandle } from "./editor/CommentEditor";

/** 单条评论（支持点赞/回复标识/删除/回复按钮；html 评论走 RichContent，旧数据走 Markdown） */
function CommentItem({
  c,
  parent,
  isReply = false,
  canDelete,
  onReply,
  onDelete,
  onLike,
}: {
  c: Comment;
  // 直接父评论（父级缺失时提升后不渲染“回复 xxx”行）
  parent?: Comment | null;
  isReply?: boolean;
  canDelete: boolean;
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
          {c.content_format === "html" ? <RichContent content={c.content} /> : <Markdown content={c.content} />}
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

/** 回溯层数上限：防环双保险之一（与旧版 50 跳一致） */
const MAX_DEPTH = 50;

/**
 * 沿 parent_id 向上回溯到「最近存在的顶层祖先」：
 * - 返回评论自身：父级缺失且链上无任何已存在祖先 → 提升为顶层展示；
 * - 成环（或自指）时同样按顶层展示，避免整链评论消失；
 * - seen + MAX_DEPTH 双保险，保证不悬挂/死循环。
 */
function findRoot(c: Comment, parentMap: Record<string, Comment>): Comment {
  const seen = new Set<string>([c.id]);
  let cur = c;
  let guard = 0;
  while (cur.parent_id && guard < MAX_DEPTH) {
    const parent = parentMap[cur.parent_id];
    if (!parent) break;
    if (seen.has(parent.id)) return c; // 成环：无有效根 → 提升为顶层
    seen.add(parent.id);
    cur = parent;
    guard++;
  }
  return cur;
}

/**
 * 评论区（UI 单层归并视图）：
 * - 所有后代平铺到最近存在的顶层祖先（根）的回复组，标「回复 @直接父级」；
 *   父级缺失且链上无已存在祖先时提升为顶层；
 * - 根评论最新在前；回复组内时间升序；折叠时默认只显示最新 2 条，展开显示全部；
 * - 锚点（#comment-xxx，目标存在）默认展开所在组；用户收起/展开优先；
 * - 点「回复」自动展开目标根组；seen + MAX_DEPTH 防环。
 */
export default function CommentSection({
  comments,
  userId,
  editorRef,
  replyText,
  replyTo,
  setReplyTo,
  onChangeReplyText,
  onSubmit,
  onDelete,
  onLike,
  submitting,
  canWrite = true,
}: {
  comments: Comment[];
  userId: string | null;
  editorRef: React.RefObject<CommentEditorHandle | null>;
  // 编辑器当前 HTML（受控）
  replyText: string;
  replyTo: { id: string; name: string } | null;
  setReplyTo: (v: { id: string; name: string } | null) => void;
  onChangeReplyText: (html: string) => void;
  onSubmit: (altcha?: string) => void;
  onDelete: (id: string) => void;
  onLike: (c: Comment) => void;
  /** 提交中：禁用发送按钮，防双击重复 */
  submitting: boolean;
  /** 是否允许写入评论（需服务端已验证的登录态；不能只信 user_id Cookie） */
  canWrite?: boolean;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // 评论框吸附顶栏：哨兵离开「顶栏下方可视区」即视为贴住（此时两侧上圆角改为直角）
  const [stuck, setStuck] = useState(false);
  const stickySentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = stickySentinelRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      // 仅「哨兵越过顶栏（在视口上方）」才算吸顶；哨兵在视口下方时 isIntersecting 也是 false
      ([entry]) => setStuck(!entry.isIntersecting && entry.boundingClientRect.top < 70),
      { rootMargin: "-70px 0px 0px 0px", threshold: 0 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [userId]);

  const { mainComments, replyMap, parentMap } = useMemo(() => {
    const parentMap: Record<string, Comment> = {};
    comments.forEach((c) => {
      parentMap[c.id] = c;
    });
    // 归并：后代沿 parent_id 回溯到最近存在的顶层祖先；父级缺失且无已存在祖先 → 提升为顶层
    const replyMap: Record<string, Comment[]> = {};
    const promoted = new Set<string>();
    comments.forEach((c) => {
      if (!c.parent_id) return;
      const root = findRoot(c, parentMap);
      if (root.id === c.id) {
        promoted.add(c.id);
        return;
      }
      if (!replyMap[root.id]) replyMap[root.id] = [];
      replyMap[root.id].push(c);
    });
    Object.keys(replyMap).forEach((rootId) => {
      replyMap[rootId].sort((a, b) => new Date(a.created_at || "").getTime() - new Date(b.created_at || "").getTime());
    });
    // 顶层 = 真根评论 + 提升的缺失父级评论；保持服务端顺序反转（最新在前）
    const mainComments = comments.filter((c) => !c.parent_id || promoted.has(c.id)).reverse();
    return { mainComments, replyMap, parentMap };
  }, [comments]);

  // 锚点（#comment-xxx）：仅当目标评论真实存在时，默认展开其所在回复组（不覆盖用户操作）
  const anchorCommentId =
    typeof window !== "undefined" && window.location.hash.startsWith("#comment-")
      ? decodeURIComponent(window.location.hash.slice("#comment-".length))
      : null;
  const anchorTarget = anchorCommentId ? parentMap[anchorCommentId] : undefined;
  const anchorRootId = anchorTarget ? findRoot(anchorTarget, parentMap).id : null;

  /** 回复点击：展开目标评论所在的根组，确保发送成功后新回复立即可见 */
  const startingReply = (c: Comment) => {
    const root = findRoot(c, parentMap);
    setExpanded((p) => ({ ...p, [root.id]: true }));
    setReplyTo({ id: c.id, name: c.user_name || "匿名" });
    editorRef.current?.focus();
  };

  return (
    <>
      <div className="comment-section-title">评论区</div>
      {canWrite ? (
        <>
          <div ref={stickySentinelRef} className="comment-sticky-sentinel" aria-hidden="true" />
          <div className={`comment-input-bar${stuck ? " is-stuck" : ""}`}>
            {replyTo && (
              <div className="comment-reply-indicator">
                <span>
                  回复 <b className="Username">{replyTo.name}</b>
                </span>
                <button onClick={() => setReplyTo(null)}><i className="fa fa-times"></i></button>
              </div>
            )}
            <CommentEditor
              value={replyText}
              onChange={onChangeReplyText}
              onSubmit={onSubmit}
              placeholder={replyTo ? `回复 ${replyTo.name}…` : "写下你的评论…"}
              editorRef={editorRef}
              submitting={submitting}
              captcha
            />
          </div>
        </>
      ) : (
        <div className="comment-login-gate">
          <i className="fa fa-lock"></i>
          <span>登录后即可参与评论</span>
          <Link href="/auth" className="comment-login-btn">去登录</Link>
        </div>
      )}
      <div className="comment-list" id="comment-list">
        {comments.length === 0 ? (
          <div className="comment-empty">暂无评论，快来抢沙发~</div>
        ) : (
          mainComments.map((c) => {
            const replies = replyMap[c.id] || [];
            const hiddenCount = Math.max(0, replies.length - 2);
            // 用户操作优先；否则锚点目标所在组默认展开
            const shown = expanded[c.id] ?? c.id === anchorRootId;
            const visibleReplies = shown ? replies : replies.slice(-2);
            return (
              <div key={c.id}>
                <CommentItem
                  c={c}
                  canDelete={!!userId && userId === c.user_id}
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
                        parent={r.parent_id ? parentMap[r.parent_id] : undefined}
                        isReply
                        canDelete={!!userId && userId === r.user_id}
                        onReply={startingReply}
                        onDelete={onDelete}
                        onLike={onLike}
                      />
                    ))}
                    {hiddenCount > 0 && (
                      <button
                        className="comment-replies-toggle"
                        data-parent-id={c.id}
                        onClick={() => setExpanded((p) => ({ ...p, [c.id]: !shown }))}
                      >
                        <i className={`fa ${shown ? "fa-chevron-up" : "fa-chevron-down"}`}></i>{" "}
                        {shown ? "收起回复" : `展开${hiddenCount}条回复`}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
