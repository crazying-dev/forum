"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import PostCard from "@/components/PostCard";
import FollowListModal from "@/components/FollowListModal";
import UserProfileModal from "@/components/UserProfileModal";
import { ProfilePrefixBadge } from "@/components/PrefixBadge";
import CategoryBadge from "@/components/ui/CategoryBadge";
import { useToast } from "@/components/Toast";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { userApi, postApi, User, Post, UserBrief, ReplyItem, ApiException, GuildMembership } from "@/lib/api";
import { ageDisplay, themeColor, themeTint } from "@/lib/constants";
import { useStore } from "@/lib/store";

function fmtDate(v?: string) {
  if (!v) return "-";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function UserPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user: me, userId, refreshUser } = useStore();
  const { toast } = useToast();
  const [profile, setProfile] = useState<User | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [followStats, setFollowStats] = useState<any>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [isFollowing, setIsFollowing] = useState(false);
  const [isSelf, setIsSelf] = useState(false);
  const [guild, setGuild] = useState<GuildMembership | null>(null);
  const [isLeader, setIsLeader] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showFollowList, setShowFollowList] = useState<null | "following" | "followers">(null);
  const [followUsers, setFollowUsers] = useState<UserBrief[]>([]);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [activeTab, setActiveTab] = useState<"posts" | "comments">("posts");
  const [postView, setPostView] = useState<"posts" | "favorites">("posts");
  const [comments, setComments] = useState<ReplyItem[] | null>(null);
  const [favorites, setFavorites] = useState<Post[] | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await userApi.profile(id);
      setProfile(r.user);
      setStats(r.stats);
      setFollowStats(r.follow_stats);
      setIsFollowing(!!r.is_following);
      setIsSelf(!!r.is_self || userId === id);
      setGuild(r.guild || null);
      setIsLeader(!!r.is_leader);
      const p = await userApi.posts(id, 1, 20);
      setPosts(p.posts || []);
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "用户不存在", "error");
    } finally {
      setLoading(false);
    }
  }, [id, userId, toast]);

  useEffect(() => { load(); }, [load]);

  const loadComments = useCallback(async () => {
    try {
      const r = await userApi.comments(id, 1, 50);
      setComments(r.comments || []);
    } catch {
      setComments([]);
    }
  }, [id]);

  useEffect(() => {
    if (activeTab === "comments" && comments === null) loadComments();
  }, [activeTab, comments, loadComments]);

  const loadFavorites = useCallback(async () => {
    try {
      const r = await userApi.favorites(id, 1, 50);
      setFavorites(r.posts || []);
    } catch {
      setFavorites([]);
    }
  }, [id]);

  useEffect(() => {
    if (postView === "favorites" && favorites === null) loadFavorites();
  }, [postView, favorites, loadFavorites]);

  const toggleFollow = async () => {
    if (!me) return router.push("/auth");
    try {
      const r = await userApi.follow(id);
      setIsFollowing(r.following);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const openFollowList = async (kind: "following" | "followers") => {
    setShowFollowList(kind);
    try {
      const r = kind === "following" ? await userApi.following(id) : await userApi.followers(id);
      setFollowUsers(r.users || []);
    } catch { setFollowUsers([]); }
  };

  const sendVerifyEmail = async () => {
    try {
      await userApi.verifyEmail();
      const code = window.prompt("验证码已发送至你的邮箱，请输入收到的 6 位验证码：");
      if (!code) return;
      await userApi.verifyEmailConfirm(code.trim());
      toast("邮箱验证成功", "success");
      await refreshUser();
      load();
    } catch (e: any) {
      toast(e instanceof ApiException ? e.message : "操作失败", "error");
    }
  };

  const onProfileSaved = async () => {
    await refreshUser();
    load();
  };

  const onToggleFollowInList = async (u: UserBrief) => {
    try {
      await userApi.follow(u.id);
      setFollowUsers((list) => list.map((x) => (x.id === u.id ? { ...x, is_following: !x.is_following } : x)));
    } catch { /* 忽略 */ }
  };

  if (loading) return <div className="loading-text" style={{ padding: 40 }}>加载中...</div>;
  if (!profile) return <div className="loading-text" style={{ padding: 40 }}>用户不存在</div>;

  const vipIcon = profile.vip && profile.vip !== "0" ? (
    <span className="user-vip-icon" style={{ display: "inline-flex" }}>
      <i className="fa fa-diamond" style={{ color: "#f59e0b", fontSize: 18 }}></i>
    </span>
  ) : null;

  return (
    <>
      <div className="user-profile-page">
        <div className="user-profile-card">
          <div className="user-profile-avatar-wrapper">
            <div className="user-profile-avatar">
              <UserAvatar src={profile.avatar} alt="用户头像" imgId="user-profile-avatar-img" fallbackClassName="avatar-fallback avatar-fallback-lg" />
            </div>
            <ProfilePrefixBadge prefix={profile.prefix} />
          </div>
          <div className="user-profile-info">
            <h2>
              <div id="user-profile-name" className="user-name-clickable Username" title="点击查看详情" onClick={() => setShowProfileModal(true)}>
                {profile.name}
              </div>
              {vipIcon}
            </h2>
            <p className="user-profile-intro" id="user-profile-intro">{profile.intro || "这个人很懒，什么都没留下~"}</p>
            <div className="user-profile-meta">
              <span className="user-meta-item user-meta-clickable" id="user-profile-gender" title="点击查看详情" onClick={() => setShowProfileModal(true)}>
                <i className="fa fa-user"></i> {profile.gender === 1 ? "男" : profile.gender === 2 ? "女" : "保密"}
              </span>
              <span className="user-meta-item user-meta-clickable" id="user-profile-age" title="点击查看详情" onClick={() => setShowProfileModal(true)}>
                <i className="fa fa-birthday-cake"></i> {ageDisplay(profile.age)}
              </span>
              {profile.email_verified === 1 ? (
                <span className="user-meta-item email-verified-badge" id="user-profile-email-verified-meta" title="邮箱已验证">
                  <i className="fa fa-envelope"></i> 已验证
                </span>
              ) : (
                isSelf && (
                  <button type="button" className="user-meta-item user-meta-clickable email-verify-btn" id="user-profile-verify-email" onClick={sendVerifyEmail}>
                    <i className="fa fa-envelope"></i> 验证邮箱
                  </button>
                )
              )}
            </div>
            <div className="user-guild-row" id="user-profile-guild">
              {guild ? (
                <>
                  <Link
                    className="user-guild-tag"
                    href={`/huiguan/${guild.slug}`}
                    title={`进入会馆「${guild.name}」`}
                    style={{ background: themeTint(guild.theme_color), color: themeColor(guild.theme_color) }}
                  >
                    <i className="fa fa-home"></i> {guild.name}
                  </Link>
                  {isLeader && (
                    <span className="user-guild-leader-tag" style={{ background: themeTint(guild.theme_color), color: themeColor(guild.theme_color) }}>
                      <i className="fa fa-crown"></i> 馆长
                    </span>
                  )}
                </>
              ) : (
                <span className="user-guild-tag user-guild-none" id="user-profile-no-guild">
                  <i className="fa fa-home"></i> 未加入会馆
                </span>
              )}
            </div>
          </div>
          <div className="user-profile-stats">
            <div className="stat-item">
              <span className="stat-number" id="user-post-count">{stats?.post_count || 0}</span>
              <span className="stat-label">帖子</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" id="user-total-likes">{stats?.total_likes || 0}</span>
              <span className="stat-label">获赞</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" id="user-total-views">{stats?.total_views || 0}</span>
              <span className="stat-label">浏览</span>
            </div>
            <div className="stat-item stat-item-clickable" onClick={() => openFollowList("following")}>
              <span className="stat-number" id="user-following-count">{followStats?.following_count || 0}</span>
              <span className="stat-label">关注</span>
            </div>
            <div className="stat-item stat-item-clickable" onClick={() => openFollowList("followers")}>
              <span className="stat-number" id="user-follower-count">{followStats?.follower_count || 0}</span>
              <span className="stat-label">粉丝</span>
            </div>
          </div>
          {!isSelf && (
            <button className={`user-follow-btn ${isFollowing ? "following" : ""}`} id="user-follow-btn" onClick={toggleFollow}>
              {isFollowing ? "已关注" : "+ 关注"}
            </button>
          )}
        </div>

        <div className="user-profile-tabs">
          <button className={`profile-tab ${activeTab === "posts" ? "active" : ""}`} data-tab="posts" onClick={() => setActiveTab("posts")}>
            <i className="fa fa-file-text"></i> 帖子列表
          </button>
          <button className={`profile-tab ${activeTab === "comments" ? "active" : ""}`} data-tab="comments" onClick={() => setActiveTab("comments")}>
            <i className="fa fa-comment-o"></i> 评论列表
          </button>
          {isSelf && (
            <Link href="/post/create" className="profile-tab profile-tab-create">
              <i className="fa fa-pencil"></i> 发布新帖
            </Link>
          )}
        </div>

        <div className="user-profile-content">
          {activeTab === "posts" ? (
            <div>
              {isSelf && (
                <div className="profile-sub-tabs">
                  <button
                    className={`profile-sub-tab ${postView === "posts" ? "active" : ""}`}
                    onClick={() => setPostView("posts")}
                  >
                    <i className="fa fa-file-text"></i> 帖子
                  </button>
                  <button
                    className={`profile-sub-tab ${postView === "favorites" ? "active" : ""}`}
                    onClick={() => setPostView("favorites")}
                  >
                    <i className="fa fa-bookmark"></i> 我的收藏
                  </button>
                </div>
              )}
              {postView === "posts" ? (
                <div id="user-posts-list" className="user-posts-list">
              {posts.length === 0 ? (
                <p className="loading-text">还没有发布帖子</p>
              ) : (
                posts.map((p) => (
                  <div className="post-item" key={p.id} style={{ cursor: "pointer" }} onClick={() => router.push(`/post/${p.id}`)}>
                    <h3 className="post-item-title">{p.title}</h3>
                    <p className="post-item-summary">{(p.summary || "").replace(/<[^>]+>/g, "").substring(0, 200)}</p>
                    <div className="post-item-footer">
                      <CategoryBadge category={p.category} className="post-item-category" />
                      <div className="post-item-stats">
                        <span><i className="fa fa-eye"></i> {p.views || 0}</span>
                        <span><i className="fa fa-thumbs-up"></i> {p.likes || 0}</span>
                        <span><i className="fa fa-comment"></i> {p.comment_count ?? 0}</span>
                        <span><i className="fa fa-clock-o"></i> {fmtDate(p.created_at)}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
              </div>
            ) : (
              <div className="user-posts-list">
                {favorites === null ? (
                  <p className="loading-text">加载中...</p>
                ) : favorites.length === 0 ? (
                  <p className="loading-text">还没有收藏帖子</p>
                ) : (
                  favorites.map((p) => (
                    <div className="post-item" key={p.id} style={{ cursor: "pointer" }} onClick={() => router.push(`/post/${p.id}`)}>
                      <div className="post-item-header">
                        <img className="post-item-avatar" src={p.user_avatar} alt="" />
                        <div className="post-item-header-body">
                          <h3 className="post-item-title">{p.title}</h3>
                          <div className="post-item-sub-meta">
                            <span className="post-item-author Username"><i className="fa fa-user-circle-o"></i> {p.user_name}</span>
                            <CategoryBadge category={p.category} className="post-item-category" />
                          </div>
                        </div>
                      </div>
                      <p className="post-item-summary">{(p.summary || "").replace(/<[^>]+>/g, "").substring(0, 200)}</p>
                      <div className="post-item-footer post-item-footer-right">
                        <div className="post-item-stats">
                          <span><i className="fa fa-eye"></i> {p.views || 0}</span>
                          <span><i className="fa fa-thumbs-up"></i> {p.likes || 0}</span>
                          <span><i className="fa fa-comment"></i> {p.comment_count ?? 0}</span>
                          <span><i className="fa fa-clock-o"></i> {fmtDate(p.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="user-comments-list">
            {comments === null ? (
              <p className="loading-text">加载中...</p>
            ) : comments.length === 0 ? (
              <p className="loading-text">还没有发表评论</p>
            ) : (
              comments.map((c) => (
                <Link
                  className="comment-item"
                  key={c.id}
                  href={`/post/${c.post_id}#comment-${c.id}`}
                  title="点击跳转到该评论"
                >
                  <div className="comment-avatar">
                    <img src={c.user_avatar} alt="" />
                  </div>
                  <div className="comment-body">
                    <div className="comment-header">
                      <span className="comment-author">{c.user_name}</span>
                      <span className="comment-time">{fmtDate(c.created_at)}</span>
                    </div>
                    <div className="comment-text">{c.content}</div>
                    <div className="comment-footer">
                      <span className="comment-post-link">
                        <i className="fa fa-commenting-o"></i> 评论于「{c.post_title}」
                      </span>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        )}
        </div>
      </div>

      {showProfileModal && profile && (
        <UserProfileModal profile={profile} isSelf={isSelf} onClose={() => setShowProfileModal(false)} onSaved={onProfileSaved} />
      )}

      {showFollowList && (
        <FollowListModal
          title={showFollowList === "following" ? "关注列表" : "粉丝列表"}
          users={followUsers}
          currentUserId={userId}
          onClose={() => setShowFollowList(null)}
          onTabChange={(tab) => openFollowList(tab)}
          onToggleFollow={onToggleFollowInList}
        />
      )}
    </>
  );
}
