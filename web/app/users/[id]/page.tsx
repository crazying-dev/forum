"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import PostCard from "@/components/PostCard";
import FollowListModal, { FollowTab } from "@/components/FollowListModal";
import UserProfileModal from "@/components/UserProfileModal";
import EmailChangeModal from "@/components/EmailChangeModal";
import CategoryBadge from "@/components/ui/CategoryBadge";
import SpaceBadge from "@/components/ui/SpaceBadge";
import Markdown from "@/components/Markdown";
import RichContent from "@/components/ui/RichContent";
import HoverTip from "@/components/ui/HoverTip";
import { useToast } from "@/components/Toast";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { userApi, postApi, User, Post, UserBrief, ReplyItem, ApiException, GuildMembership } from "@/lib/api";
import { ageDisplay, contrastText, themeColor } from "@/lib/constants";
import { useStore } from "@/lib/store";

function fmtDate(v?: string) {
  if (!v) return "-";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Asia/Shanghai 日期 YYYY-MM-DD（签到初始态与 last_sign_in 比对，与服务端签到日界一致） */
function shanghaiDateStr() {
  // 用 formatToParts 手动拼接，避免部分环境 en-CA 输出格式差异
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** 定时发布时间展示（YYYY-MM-DD HH:mm，本地时区） */
function fmtDateTime(v?: string) {
  if (!v) return "";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "";
  return `${fmtDate(v)} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** published_at 在未来即定时未发布（本人可见） */
function isScheduled(v?: string) {
  return !!v && new Date(v).getTime() > Date.now();
}

/** 馆长提示中的会馆名（名称已以「会馆」结尾则不重复追加） */
function guildTitle(name: string) {
  return name.endsWith("会馆") ? name : `${name}会馆`;
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
  const [showFollowList, setShowFollowList] = useState<FollowTab | null>(null);
  const [followUsers, setFollowUsers] = useState<UserBrief[]>([]);
  const [followHasMore, setFollowHasMore] = useState(false);
  const [followLoadingMore, setFollowLoadingMore] = useState(false);
  const followPageRef = useRef(1);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showEmailChange, setShowEmailChange] = useState(false);
  const [activeTab, setActiveTab] = useState<"posts" | "comments">("posts");
  const [postView, setPostView] = useState<"posts" | "favorites">("posts");
  const [comments, setComments] = useState<ReplyItem[] | null>(null);
  const [favorites, setFavorites] = useState<Post[] | null>(null);
  // 签到：初始态用 last_sign_in 与 Asia/Shanghai 日期比对；409 视为今日已签
  const [signedToday, setSignedToday] = useState(false);
  const [signingIn, setSigningIn] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await userApi.profile(id);
      setProfile(r.user);
      // 已注销用户：仅最小档案，不请求帖子/评论等列表数据
      if (r.user.deleted) {
        setStats(null);
        setFollowStats(null);
        setIsFollowing(false);
        setIsSelf(false);
        setGuild(null);
        setIsLeader(false);
        setPosts([]);
        return;
      }
      setSignedToday(!!r.user.last_sign_in && r.user.last_sign_in === shanghaiDateStr());
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

  /** 每日签到：成功更新灵力值；409 置为已签 */
  const doSignIn = async () => {
    if (signingIn || signedToday) return;
    setSigningIn(true);
    try {
      const r = await userApi.signIn();
      setSignedToday(true);
      setProfile((p) => (p ? { ...p, spirit: r.data.spirit, last_sign_in: r.data.last_sign_in } : p));
      toast("签到成功，灵力值 +10", "success");
    } catch (e: unknown) {
      if (e instanceof ApiException && e.status === 409) {
        setSignedToday(true);
        toast("今日已签到", "info");
      } else {
        toast(e instanceof ApiException ? e.message : "签到失败，请稍后再试", "error");
      }
    } finally {
      setSigningIn(false);
    }
  };

  const toggleFollow = async () => {
    if (!me) return router.push("/auth");
    try {
      const r = await userApi.follow(id);
      setIsFollowing(r.following);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  // 关注列表：打开/切 Tab 拉第 1 页；加载更多 page+1 追加（seq 校验：慢响应不得写入已切走的 Tab）
  const followSeqRef = useRef(0);
  const loadFollow = useCallback(
    async (tab: FollowTab, pageNo: number, append: boolean) => {
      const seq = ++followSeqRef.current;
      try {
        const r =
          tab === "following"
            ? await userApi.following(id, pageNo)
            : tab === "followers"
              ? await userApi.followers(id, pageNo)
              : await userApi.mutual(id, pageNo);
        if (seq !== followSeqRef.current) return; // 已切换 Tab/关闭，丢弃过期响应
        setFollowUsers((prev) => (append ? [...prev, ...(r.users || [])] : r.users || []));
        setFollowHasMore(!!r.has_more);
      } catch {
        if (seq !== followSeqRef.current) return;
        if (!append) setFollowUsers([]);
        setFollowHasMore(false);
      } finally {
        if (seq === followSeqRef.current) setFollowLoadingMore(false);
      }
    },
    [id]
  );

  const openFollowList = (kind: FollowTab) => {
    setShowFollowList(kind);
    setFollowUsers([]);
    setFollowHasMore(false);
    followPageRef.current = 1;
    loadFollow(kind, 1, false);
  };

  const loadMoreFollow = () => {
    if (!showFollowList) return;
    followPageRef.current += 1;
    setFollowLoadingMore(true);
    loadFollow(showFollowList, followPageRef.current, true);
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
      if (showFollowList === "mutual") {
        // 共同关注中取消关注 → 该行不再属于共同关注
        setFollowUsers((list) => list.filter((x) => x.id !== u.id));
      } else {
        setFollowUsers((list) =>
          list.map((x) =>
            x.id === u.id ? { ...x, is_following: !x.is_following, is_mutual: x.is_following ? false : x.is_mutual } : x
          )
        );
      }
    } catch { /* 忽略 */ }
  };

  // 共同关注 Tab：仅登录且非本人主页时展示
  const showMutualTab = !isSelf && !!me;

  if (loading) return <div className="loading-text" style={{ padding: 40 }}>加载中...</div>;
  if (!profile) return <div className="loading-text" style={{ padding: 40 }}>用户不存在</div>;

  // 已注销用户：简洁态（默认头像 + 说明文案，隐藏 Tab/帖子列表/关注等交互）
  if (profile.deleted) {
    return (
      <div className="user-profile-page">
        <div className="user-profile-card user-profile-deleted">
          <div className="user-profile-avatar-wrapper">
            <div className="user-profile-avatar">
              <i className="fa fa-user avatar-fallback avatar-fallback-lg"></i>
            </div>
          </div>
          <div className="user-profile-info">
            <h2>
              <span className="user-profile-deleted-name">已注销账户</span>
            </h2>
            <p className="user-profile-intro">该账号已注销，内容已匿名化保留</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="user-profile-page">
        <div className="user-profile-card">
          <div className="user-profile-avatar-wrapper">
            <div className="user-profile-avatar">
              <UserAvatar
                src={profile.avatar}
                alt="用户头像"
                imgId="user-profile-avatar-img"
                fallbackClassName="avatar-fallback avatar-fallback-lg"
                userId={profile.id}
              />
            </div>
          </div>
          <div className="user-profile-info">
            <h2>
              <div id="user-profile-name" className="user-name-clickable Username" title="点击查看详情" onClick={() => setShowProfileModal(true)}>
                {profile.name}
              </div>
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
                  <HoverTip text={`进入会馆「${guild.name}」`}>
                    <Link
                      className="user-guild-tag"
                      href={`/huiguan/${guild.slug}`}
                      style={{ background: themeColor(guild.theme_color), color: contrastText(themeColor(guild.theme_color)) }}
                    >
                      <i className="fa fa-home"></i> {guild.name}
                    </Link>
                  </HoverTip>
                  {isLeader && (
                    <HoverTip text={`TA 是「${guildTitle(guild.name)}」的馆长`}>
                      <span className="user-guild-chip user-leader-chip">
                        <i className="fa fa-crown"></i> 馆长
                      </span>
                    </HoverTip>
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
            <div className="stat-item">
              <span className="stat-number" id="user-spirit">{profile.spirit ?? 0}</span>
              <span className="stat-label">灵力值</span>
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
          {isSelf && (
            <button
              className={`user-follow-btn user-signin-btn ${signedToday ? "signed" : ""}`}
              id="user-signin-btn"
              disabled={signingIn || signedToday}
              onClick={doSignIn}
            >
              <i className="fa fa-calendar-check-o"></i>
              <span className="user-signin-label user-signin-label-desktop">{signedToday ? "今日已签到" : "今日签到 +10"}</span>
              <span className="user-signin-label user-signin-label-mobile">{signedToday ? "已签到" : "签到"}</span>
            </button>
          )}
          {isSelf && !profile.deleted && (
            <div className="user-account-settings" id="user-account-settings">
              <span className="user-account-settings-label"><i className="fa fa-cog"></i> 账号设置</span>
              <button type="button" className="account-settings-btn" onClick={() => setShowEmailChange(true)}>
                <i className="fa fa-envelope-o"></i> 更换邮箱
              </button>
              <Link href="/account/delete" className="account-settings-btn account-settings-danger">
                <i className="fa fa-user-times"></i> 注销账号
              </Link>
            </div>
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
                      <div className="post-item-tags">
                        <CategoryBadge category={p.category} className="post-item-category" />
                        <SpaceBadge name={p.guild_name} color={p.guild_theme_color} />
                      </div>
                      <div className="post-item-stats">
                        <span><i className="fa fa-eye"></i> {p.views || 0}</span>
                        <span><i className="fa fa-thumbs-up"></i> {p.likes || 0}</span>
                        <span><i className="fa fa-comment"></i> {p.comment_count ?? 0}</span>
                        <span><i className="fa fa-clock-o"></i> {fmtDate(p.created_at)}</span>
                      </div>
                      {isSelf && isScheduled(p.published_at) && (
                        <span className="post-scheduled-tag-wrap">
                          <span className="post-scheduled-tag" title="尚未到达发布时间，仅自己可见">
                            <i className="fa fa-clock-o"></i> 定时发布 {fmtDateTime(p.published_at)}
                          </span>
                        </span>
                      )}
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
                        <div className="post-item-avatar">
                          <UserAvatar src={p.user_avatar} userId={p.user_id} />
                        </div>
                        <div className="post-item-header-body">
                          <h3 className="post-item-title">{p.title}</h3>
                          <div className="post-item-sub-meta">
                            <span className="post-item-author Username"><i className="fa fa-user-circle-o"></i> {p.user_name}</span>
                            <CategoryBadge category={p.category} className="post-item-category" />
                            <SpaceBadge name={p.guild_name} color={p.guild_theme_color} />
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
              comments.map((c) => {
                const href = `/post/${c.post_id}#comment-${c.id}`;
                return (
                  <div
                    className="comment-item comment-item-clickable"
                    key={c.id}
                    role="link"
                    tabIndex={0}
                    title="点击跳转到该评论"
                    onClick={(e) => {
                      // 正文内的链接（超链接/引用卡）自行处理跳转，不触发整卡跳转
                      if ((e.target as HTMLElement).closest("a")) return;
                      router.push(href);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") router.push(href);
                    }}
                  >
                    <div className="comment-avatar">
                      <UserAvatar src={c.user_avatar} userId={c.user_id} />
                    </div>
                    <div className="comment-body">
                      <div className="comment-header">
                        <span className="comment-author">{c.user_name}</span>
                        <span className="comment-time">{fmtDate(c.created_at)}</span>
                      </div>
                      <div className="comment-text">
                        {c.content_format === "html" ? <RichContent content={c.content} /> : <Markdown content={c.content} />}
                      </div>
                      <div className="comment-footer">
                        <Link className="comment-post-link" href={href} onClick={(e) => e.stopPropagation()}>
                          <i className="fa fa-commenting-o"></i> 评论于「{c.post_title}」
                        </Link>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
        </div>
      </div>

      {showProfileModal && profile && (
        <UserProfileModal profile={profile} isSelf={isSelf} onClose={() => setShowProfileModal(false)} onSaved={onProfileSaved} />
      )}

      {showEmailChange && (
        <EmailChangeModal onClose={() => setShowEmailChange(false)} />
      )}

      {showFollowList && (
        <FollowListModal
          activeTab={showFollowList}
          users={followUsers}
          currentUserId={userId}
          isSelf={isSelf}
          showMutualTab={showMutualTab}
          hasMore={followHasMore}
          loadingMore={followLoadingMore}
          onClose={() => setShowFollowList(null)}
          onTabChange={(tab) => openFollowList(tab)}
          onLoadMore={loadMoreFollow}
          onToggleFollow={onToggleFollowInList}
        />
      )}
    </>
  );
}
