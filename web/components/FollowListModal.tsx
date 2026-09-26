"use client";

import Link from "next/link";
import type { UserBrief } from "@/lib/api";
import { LoadMoreButton } from "./ui/ListState";
import Modal from "./ui/Modal";
import { UserAvatar } from "./ui/UserAvatar";

// 关注列表 Tab：关注 / 粉丝 / 共同关注
export type FollowTab = "following" | "followers" | "mutual";

/** 关注列表弹窗（标题/三 Tab/列表项/关注按钮/加载更多） */
export default function FollowListModal({
  activeTab,
  users,
  currentUserId,
  isSelf,
  showMutualTab,
  hasMore,
  loadingMore,
  onClose,
  onTabChange,
  onLoadMore,
  onToggleFollow,
}: {
  activeTab: FollowTab;
  users: UserBrief[];
  currentUserId: string | null;
  isSelf: boolean;
  showMutualTab: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onClose: () => void;
  onTabChange: (tab: FollowTab) => void;
  onLoadMore: () => void;
  onToggleFollow: (user: UserBrief) => Promise<void>;
}) {
  const title = activeTab === "following" ? "关注列表" : activeTab === "followers" ? "粉丝列表" : "共同关注";
  const emptyText =
    activeTab === "following"
      ? isSelf
        ? "还没有关注任何人"
        : "TA 还没有关注任何人"
      : activeTab === "followers"
        ? isSelf
          ? "还没有粉丝"
          : "TA 还没有粉丝"
        : "暂无共同关注";

  const toggle = async (u: UserBrief) => {
    await onToggleFollow(u);
  };

  return (
    <Modal
      open
      onClose={onClose}
      className="follow-list-modal"
      overlayClassName="follow-list-overlay"
      cardClassName="follow-list-container"
      closeable={false}
    >
      <div className="follow-list-header">
        <h3 id="follow-list-title">{title}</h3>
        <button className="follow-list-close" onClick={onClose}>&times;</button>
      </div>
      <div className="follow-list-tabs">
        <button className={`follow-tab ${activeTab === "following" ? "active" : ""}`} data-type="following" onClick={() => onTabChange("following")}>关注</button>
        <button className={`follow-tab ${activeTab === "followers" ? "active" : ""}`} data-type="followers" onClick={() => onTabChange("followers")}>粉丝</button>
        {showMutualTab && (
          <button className={`follow-tab ${activeTab === "mutual" ? "active" : ""}`} data-type="mutual" onClick={() => onTabChange("mutual")}>共同关注</button>
        )}
      </div>
      <div id="follow-list-content" className="follow-list-content">
        {users.length === 0 ? (
          <p className="loading-text" style={{ textAlign: "center" }}>{emptyText}</p>
        ) : (
          users.map((u) => {
            const isItemSelf = currentUserId === u.id;
            const vipBadge = u.vip && u.vip !== "0" ? (
              <span className="follow-user-vip"><i className="fa fa-diamond"></i></span>
            ) : null;
            return (
              <div className="follow-user-item" key={u.id}>
                <Link href={`/users/${u.id}`} className="follow-user-avatar">
                  <UserAvatar src={u.avatar} alt={u.name} />
                  {vipBadge}
                </Link>
                <div className="follow-user-info">
                  <div className="follow-user-name-row">
                    <Link href={`/users/${u.id}`} className="follow-user-name Username">{u.name}</Link>
                    {/* 关注列表：对方也关注了我 → 「共同关注」小胶囊 */}
                    {activeTab === "following" && u.is_mutual && <span className="follow-user-tag">共同关注</span>}
                  </div>
                  <p className="follow-user-intro">{u.intro || "这个人很懒，什么都没留下~"}</p>
                </div>
                {!isItemSelf && !u.is_self && (
                  <button
                    className={`follow-btn ${u.is_following ? "followed" : ""}`}
                    onClick={() => toggle(u)}
                  >
                    {u.is_following ? "已关注" : "关注"}
                  </button>
                )}
              </div>
            );
          })
        )}
        {hasMore && <LoadMoreButton loading={loadingMore} onClick={onLoadMore} className="follow-list-more" />}
      </div>
    </Modal>
  );
}
