"use client";

// 消息类型栏：全部（聚合）/ 赞 / 评论 / 管理团队 / 系统 + 未读徽标。

import type { MessageSummary } from "@/lib/api/messages";
import { MESSAGE_TYPE_META, MESSAGE_TYPE_ORDER, type MessageType } from "./types";

function unreadOf(type: MessageType, unread: MessageSummary): number {
  if (type === "all") return unread.likes + unread.comments + unread.system;
  if (type === "likes") return unread.likes;
  if (type === "comments") return unread.comments;
  if (type === "system") return unread.system;
  return unread.chat;
}

function badgeText(count: number): string {
  return count > 99 ? "99+" : String(count);
}

export default function MessageTypeList({
  active,
  unread,
  onSelect,
}: {
  active: MessageType;
  unread: MessageSummary;
  onSelect: (type: MessageType) => void;
}) {
  return (
    <nav className="msg-type-list" aria-label="消息类型">
      {MESSAGE_TYPE_ORDER.map((type) => {
        const meta = MESSAGE_TYPE_META[type];
        const count = unreadOf(type, unread);
        const isActive = active === type;
        return (
          <button
            key={type}
            type="button"
            className={`msg-type-item${isActive ? " active" : ""}`}
            aria-current={isActive ? "page" : undefined}
            onClick={() => onSelect(type)}
          >
            <i className={`fa ${meta.icon} msg-type-icon`} aria-hidden="true"></i>
            <span className="msg-type-label">{meta.label}</span>
            {count > 0 && (
              <span className="msg-type-badge" aria-label={`${count} 条未读`}>
                {badgeText(count)}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
