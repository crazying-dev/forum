"use client";

// 单条消息：赞 / 评论（头像 + 名称 + 动作 + 帖子标题/摘要 + 时间 + 未读点）/ 系统通知。
// 点击赞/评论条目使用 router.push 同标签跳转到帖子对应评论锚点。

import { useRouter } from "next/navigation";
import RichContent from "@/components/ui/RichContent";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { timeAgo } from "@/lib/constants";
import type { FeedItem } from "./types";

const KIND_LABEL: Record<FeedItem["kind"], string> = {
  like: "赞",
  comment: "评论",
  system: "系统",
};

function postHref(postId: string, commentId?: string): string {
  if (!postId) return "";
  return commentId ? `/post/${postId}#comment-${commentId}` : `/post/${postId}`;
}

function externalHref(link: string): string {
  if (!link) return "";
  if (/^https?:\/\//i.test(link) || link.startsWith("mailto:")) return link;
  return link.startsWith("/") ? link : `/${link}`;
}

export default function MessageItem({ item, unread = false, showKind = false }: { item: FeedItem; unread?: boolean; showKind?: boolean }) {
  const router = useRouter();

  if (item.kind === "system") {
    const link = externalHref(item.system.link);
    const open = () => {
      if (!link) return;
      if (/^https?:\/\//i.test(link) || link.startsWith("mailto:")) window.location.href = link;
      else router.push(link);
    };
    return (
      <div
        className={`msg-item msg-item-system${unread ? " is-unread" : ""}${link ? " is-link" : ""}`}
        role={link ? "link" : undefined}
        tabIndex={link ? 0 : undefined}
        onClick={open}
        onKeyDown={(e) => {
          if (link && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            open();
          }
        }}
      >
        <span className="msg-item-avatar msg-system-icon" aria-hidden="true">
          <i className="fa fa-bullhorn"></i>
        </span>
        <div className="msg-item-main">
          <div className="msg-item-head">
            <span className="msg-item-name">{item.system.title || "系统通知"}</span>
            {showKind && <span className="msg-kind">{KIND_LABEL.system}</span>}
            <span className="msg-item-time">{timeAgo(item.system.created_at)}</span>
            {unread && <span className="msg-item-dot" aria-label="未读" />}
          </div>
          {item.system.body_html && <RichContent content={item.system.body_html} className="msg-item-body msg-rich" />}
        </div>
        {link && <i className="fa fa-angle-right msg-item-arrow" aria-hidden="true"></i>}
      </div>
    );
  }

  const isLike = item.kind === "like";
  const actor = isLike ? item.like.actor : item.comment.actor;
  const postId = isLike ? item.like.post_id : item.comment.post_id;
  const postTitle = isLike ? item.like.post_title : item.comment.post_title;
  const excerpt = isLike ? item.like.comment_excerpt : item.comment.excerpt;
  const commentId = isLike ? (item.like.target_type === "comment" ? item.like.comment_id : "") : item.comment.comment_id;
  const action = isLike
    ? item.like.target_type === "post"
      ? "赞了你的帖子"
      : "赞了你的评论"
    : item.comment.parent_id
      ? "回复了你的评论"
      : "评论了你的帖子";
  const href = postHref(postId, commentId);

  return (
    <button
      type="button"
      className={`msg-item${unread ? " is-unread" : ""}${href ? " is-link" : ""}`}
      aria-label={`${actor.name} ${action}${postTitle ? `：${postTitle}` : ""}`}
      onClick={() => {
        if (href) router.push(href);
      }}
      disabled={!href}
    >
      <span className="msg-item-avatar">
        <UserAvatar src={actor.avatar} alt={`${actor.name} 的头像`} userId={actor.id} />
      </span>
      <span className="msg-item-main">
        <span className="msg-item-head">
          <span className="msg-item-name">{actor.name || "匿名"}</span>
          {showKind && <span className="msg-kind">{KIND_LABEL[item.kind]}</span>}
          <span className="msg-item-action">{action}</span>
          <span className="msg-item-time">{timeAgo(item.created_at)}</span>
          {unread && <span className="msg-item-dot" aria-label="未读" />}
        </span>
        {postTitle && <span className="msg-item-title">{postTitle}</span>}
        {excerpt && <span className="msg-item-excerpt">{excerpt}</span>}
      </span>
      {href && <i className="fa fa-angle-right msg-item-arrow" aria-hidden="true"></i>}
    </button>
  );
}
