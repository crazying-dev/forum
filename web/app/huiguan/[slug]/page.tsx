"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ArticleCard from "@/components/ArticleCard";
import GlobalLoading from "@/components/GlobalLoading";
import PostCard from "@/components/PostCard";
import { useToast } from "@/components/Toast";
import GuildLogo from "@/components/ui/GuildLogo";
import { ListEmpty, LoadMoreButton } from "@/components/ui/ListState";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ApiException, guildApi, FeedItem, GuildDetail, GuildMyState } from "@/lib/api";
import { formatUserTime, themeColor, themeTint, timeAgo } from "@/lib/constants";
import { feedItemToPost } from "@/lib/feed";
import { useCarousel } from "@/lib/useCarousel";

/** 会馆详情：信息卡 + 馆长条 + 公告轮播 + 分类筛选 + 帖子/文章混合流 */
export default function GuildDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { toast } = useToast();
  // 按 slug 记录加载结果：切换会馆时旧数据自动失效（无需在 effect 内重置）
  const [data, setData] = useState<{ slug: string; guild: GuildDetail | null; myState: GuildMyState | null; failed: boolean } | null>(null);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [bioOpen, setBioOpen] = useState(false);
  const pageRef = useRef(1);

  // 会馆详情（my_state：未登录为 null）
  useEffect(() => {
    let alive = true;
    guildApi
      .detail(slug)
      .then((r) => {
        if (alive) setData({ slug, guild: r.guild, myState: r.my_state ?? null, failed: false });
      })
      .catch(() => {
        if (alive) setData({ slug, guild: null, myState: null, failed: true });
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  const guild = data && data.slug === slug ? data.guild : null;
  const myState = data && data.slug === slug ? data.myState : null;
  const failed = !!(data && data.slug === slug && data.failed);

  // 局部更新（加入/退出后刷新展示）
  const patchData = (patch: Partial<{ guild: GuildDetail | null; myState: GuildMyState | null }>) => {
    setData((d) => (d && d.slug === slug ? { ...d, ...patch } : d));
  };

  // 内容混合流（帖子 + 文章，后端按时间倒序）
  const loadFeed = useCallback(
    async (cat: string, page: number, append: boolean) => {
      try {
        const r = await guildApi.feed(slug, page, 20, cat);
        setItems((prev) => (append ? [...prev, ...(r.items || [])] : r.items || []));
        setHasMore(!!r.has_more);
      } catch {
        if (!append) setItems([]);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [slug]
  );

  useEffect(() => {
    pageRef.current = 1;
    // 延后一个 tick 发起请求，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => loadFeed(category, 1, false), 0);
    return () => window.clearTimeout(t);
  }, [category, loadFeed]);

  const loadMore = () => {
    pageRef.current += 1;
    setLoadingMore(true);
    loadFeed(category, pageRef.current, true);
  };

  // 分类切换（用户操作）：先亮加载态再拉取
  const setCategoryChip = (name: string) => {
    if (category === name) return;
    setLoading(true);
    setCategory(name);
  };

  const announcements = guild?.announcements || [];
  const ann = useCarousel(announcements.length);

  // ---- 加入区三态 ----
  const isMember = !!myState?.is_member;
  const isPending = !!myState?.has_pending_request;

  const doJoin = async () => {
    setBusy(true);
    try {
      await guildApi.join(slug);
      patchData({ myState: { ...(myState || { is_member: false, is_leader: false }), has_pending_request: true } });
      toast("申请已提交，等待馆长审核", "success");
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "申请失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const doCancelJoin = async () => {
    setBusy(true);
    try {
      await guildApi.cancelJoin(slug);
      if (myState) patchData({ myState: { ...myState, has_pending_request: false } });
      toast("申请已撤回", "success");
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "操作失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const doLeave = async () => {
    setBusy(true);
    try {
      await guildApi.leave(slug);
      if (myState) patchData({ myState: { ...myState, is_member: false, is_leader: false } });
      if (guild) patchData({ guild: { ...guild, member_count: Math.max(0, guild.member_count - 1) } });
      toast("已退出会馆", "success");
    } catch (e) {
      // 馆长需先卸任等由后端返回 message
      toast(e instanceof ApiException ? e.message : "退出失败", "error");
    } finally {
      setBusy(false);
    }
  };

  if (failed) {
    return (
      <div className="guild-page">
        <div className="guild-empty">
          <i className="fa fa-home"></i>
          <p className="guild-empty-title">会馆不存在</p>
          <Link className="guild-empty-link" href="/huiguan">
            返回会馆广场 <i className="fa fa-arrow-right"></i>
          </Link>
        </div>
      </div>
    );
  }

  if (!guild) {
    return (
      <div className="guild-page">
        <GlobalLoading />
      </div>
    );
  }

  const theme = themeColor(guild.theme_color);

  return (
    <div className="guild-page guild-detail-page" style={{ background: `linear-gradient(180deg, ${themeTint(theme, "26")} 0%, transparent 340px)` }}>
      {/* 信息卡 */}
      <div className="guild-detail-hero" style={{ background: theme }}>
        <div className="guild-hero-shade"></div>
        <GuildLogo
          id={guild.id}
          name={guild.name}
          hasLogo={guild.has_logo}
          logoVersion={guild.logo_version}
          color={guild.theme_color}
          size={88}
          className="guild-logo guild-hero-logo"
        />
        <div className="guild-hero-body">
          <div className="guild-hero-name-row">
            <h1 className="guild-hero-name">{guild.name}</h1>
            <span className="guild-hero-id">#{guild.id}</span>
          </div>
          <p className="guild-hero-intro">{guild.intro || "这个会馆还没有简介～"}</p>
          <div className="guild-hero-meta">
            <span>
              <i className="fa fa-users"></i> {guild.member_count} 人
            </span>
            <span>
              <i className="fa fa-clock-o"></i> 创建于 {guild.created_at ? formatUserTime(guild.created_at) : "—"}
            </span>
          </div>
        </div>

        {/* 加入区 */}
        <div className="guild-join-area">
          {!myState ? (
            <Link className="guild-join-btn" href="/auth">
              <i className="fa fa-sign-in"></i> 登录后加入
            </Link>
          ) : isMember ? (
            <>
              <span className="guild-joined-badge">
                <i className="fa fa-check"></i> 已加入
              </span>
              <button className="guild-leave-btn" disabled={busy} onClick={doLeave}>
                {busy ? "处理中..." : "退出会馆"}
              </button>
            </>
          ) : isPending ? (
            <>
              <button className="guild-join-btn pending" disabled>
                <i className="fa fa-hourglass-half"></i> 审核中…
              </button>
              <button className="guild-cancel-link" disabled={busy} onClick={doCancelJoin}>
                撤回申请
              </button>
            </>
          ) : (
            <button className="guild-join-btn" disabled={busy} onClick={doJoin}>
              <i className="fa fa-plus"></i> {busy ? "提交中..." : "申请加入"}
            </button>
          )}
        </div>
      </div>

      {/* 馆长条 */}
      {guild.leader ? (
        <div className={`guild-leader-bar ${bioOpen ? "open" : ""}`}>
          <button className="guild-leader-main" onClick={() => setBioOpen(!bioOpen)}>
            <div className="guild-leader-avatar">
              <UserAvatar src={guild.leader.avatar} />
            </div>
            <div className="guild-leader-text">
              <div className="guild-leader-name">
                {guild.leader.name}
                <span className="guild-leader-tag" style={{ background: themeTint(theme), color: theme }}>
                  <i className="fa fa-crown"></i> 馆长
                </span>
              </div>
              <p className="guild-leader-intro">{guild.leader.intro || "这位馆长很低调～"}</p>
            </div>
            <i className={`fa ${bioOpen ? "fa-chevron-up" : "fa-chevron-down"} guild-leader-toggle`}></i>
          </button>
          {bioOpen && (
            <div className="guild-leader-zone">
              <div className="guild-leader-zone-title" style={{ color: theme }}>
                <i className="fa fa-star"></i> 馆长专区
              </div>
              <p className="guild-leader-bio">{guild.leader_bio || "馆长还没有留下寄语～"}</p>
              <Link className="guild-leader-link" href={`/users/${guild.leader.id}`} style={{ color: theme }}>
                查看馆长主页 <i className="fa fa-arrow-right"></i>
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="guild-leader-bar guild-leader-empty">
          <i className="fa fa-user-o"></i> 馆长虚位以待
        </div>
      )}

      {/* 公告轮播 */}
      {announcements.length > 0 && (
        <div className="guild-announce" {...ann.hoverProps}>
          <div className="guild-announce-title">
            <i className="fa fa-bullhorn"></i> 会馆公告
          </div>
          <div className="guild-announce-stage">
            {announcements.length > 1 && (
              <button className="guild-announce-arrow" aria-label="上一条公告" onClick={() => ann.go(-1)}>
                <i className="fa fa-chevron-left"></i>
              </button>
            )}
            <div className="guild-announce-body">
              <p className="guild-announce-text">{announcements[ann.index]?.content}</p>
              <span className="guild-announce-time">{timeAgo(announcements[ann.index]?.created_at)}</span>
            </div>
            {announcements.length > 1 && (
              <button className="guild-announce-arrow" aria-label="下一条公告" onClick={() => ann.go(1)}>
                <i className="fa fa-chevron-right"></i>
              </button>
            )}
          </div>
          {announcements.length > 1 && (
            <div className="guild-carousel-dots guild-announce-dots">
              {announcements.map((a, i) => (
                <button
                  key={a.id}
                  className={`guild-carousel-dot ${i === ann.index ? "active" : ""}`}
                  aria-label={`查看第 ${i + 1} 条公告`}
                  onClick={() => ann.jump(i)}
                  style={i === ann.index ? { background: theme } : undefined}
                ></button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 分类 chips（无分类则隐藏） */}
      {guild.categories.length > 0 && (
        <div className="guild-feed-cats">
          <button className={`guild-cat-chip ${category === "" ? "active" : ""}`} style={category === "" ? { background: theme } : undefined} onClick={() => setCategoryChip("")}>
            全部
          </button>
          {guild.categories.map((c) => (
            <button
              key={c.id}
              className={`guild-cat-chip ${category === c.name ? "active" : ""}`}
              style={category === c.name ? { background: theme } : undefined}
              onClick={() => setCategoryChip(c.name)}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {/* 内容混合流 */}
      <div className="guild-feed-list">
        {loading ? (
          <GlobalLoading />
        ) : items.length === 0 ? (
          <ListEmpty className="forum-empty" text={category ? "该分类下暂无内容" : "会馆里还没有内容"} />
        ) : (
          items.map((it) =>
            it.type === "article" ? (
              <ArticleCard key={`a-${it.id}`} item={it} showSpace />
            ) : (
              <PostCard key={`p-${it.id}`} post={feedItemToPost(it)} showSpace />
            )
          )
        )}
      </div>

      {hasMore && <LoadMoreButton loading={loadingMore} onClick={loadMore} id="guild-load-more" />}
    </div>
  );
}
