"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ArticleCard from "@/components/ArticleCard";
import GlobalLoading from "@/components/GlobalLoading";
import PostCard from "@/components/PostCard";
import GuildLogo from "@/components/ui/GuildLogo";
import { guildApi, FeedItem, GuildListItem } from "@/lib/api";
import { contrastText, themeColor } from "@/lib/constants";
import { feedItemToPost } from "@/lib/feed";

/** 会馆行：顶部栏（会馆名/馆长 + 进入会馆）+ 横向滚动内容区（每页 10 条，到边界自动续拉） */
function GuildFeedRow({ guild }: { guild: GuildListItem }) {
  const [visible, setVisible] = useState(false);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const pageRef = useRef(1);
  const scrollerRef = useRef<HTMLDivElement>(null);
  // 防重入：滚动事件高频触发，避免同一页被并发请求多次
  const loadingMoreRef = useRef(false);
  // 请求序号 + AbortController：卸载/切换时丢弃迟到响应，避免无谓解析与旧数据写回
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (page: number, append: boolean) => {
      if (append) {
        if (loadingMoreRef.current) return;
        loadingMoreRef.current = true;
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setError("");
      const seq = ++seqRef.current;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const r = await guildApi.feed(guild.slug, page, 10, "", ctrl.signal);
        if (seq !== seqRef.current) return;
        const list = r.items || [];
        setItems((prev) => {
          if (!append) return list;
          const seen = new Set(prev.map((x) => `${x.type}-${x.id}`));
          return [...prev, ...list.filter((x) => !seen.has(`${x.type}-${x.id}`))];
        });
        setHasMore(!!r.has_more);
        pageRef.current = page;
      } catch {
        if (ctrl.signal.aborted || seq !== seqRef.current) return;
        setError("加载失败");
        if (!append) setItems([]);
        setHasMore(false);
      } finally {
        if (seq === seqRef.current) {
          setLoading(false);
          setLoadingMore(false);
          loadingMoreRef.current = false;
        }
      }
    },
    [guild.slug]
  );

  // 卸载时中止在途请求
  useEffect(() => () => abortRef.current?.abort(), []);

  // 视口懒加载：会馆行进入可视区域（含 300px 预取边距）后才发起请求
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: "300px 0px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    // 延后一个 tick，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => load(1, false), 0);
    return () => window.clearTimeout(t);
  }, [visible, load]);

  const syncArrows = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 4);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  // 内容变化后刷新左右箭头可用态
  useEffect(() => {
    syncArrows();
  }, [items, syncArrows]);

  const onScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    syncArrows();
    // 到达右边界附近自动请求下一页（仅本行）
    if (hasMore && !loadingMoreRef.current && el.scrollLeft + el.clientWidth >= el.scrollWidth - 80) {
      load(pageRef.current + 1, true);
    }
  };

  const scrollBy = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    // 已在右边界（或内容不足一屏）时，点右箭头直接续拉下一页
    if (dir === 1 && hasMore && el.scrollLeft + el.clientWidth >= el.scrollWidth - 8) {
      load(pageRef.current + 1, true);
      return;
    }
    el.scrollBy({ left: dir * Math.max(280, el.clientWidth * 0.8), behavior: "smooth" });
  };

  const leader = guild.leader;

  return (
    <section className="guild-row" ref={sectionRef} aria-busy={loading || loadingMore}>
      <header className="guild-row-head">
        <div className="guild-row-identity">
          <GuildLogo
            logoFileId={guild.logo_file_id}
            guildUuid={guild.uuid}
            logoVersion={guild.logo_version}
            name={guild.name}
            hasLogo={guild.has_logo}
            color={guild.theme_color}
            size={40}
            className="guild-logo guild-row-logo"
          />
          <div className="guild-row-names">
            <Link className="guild-row-name" href={`/huiguan/${guild.slug}`}>
              {guild.name}
            </Link>
            <span className="guild-row-leader">
              馆长：
              {leader?.id ? (
                <Link className="guild-row-leader-link" href={`/users/${leader.id}`}>
                  {leader.name}
                </Link>
              ) : (
                "虚位以待"
              )}
            </span>
          </div>
        </div>
        <Link
          className="guild-row-enter"
          href={`/huiguan/${guild.slug}`}
          style={{ background: themeColor(guild.theme_color), color: contrastText(themeColor(guild.theme_color)) }}
        >
          进入会馆 <i className="fa fa-arrow-right"></i>
        </Link>
      </header>

      <div className="guild-row-body">
        <button
          type="button"
          className="guild-row-arrow"
          aria-label="向左滚动"
          disabled={!canLeft}
          onClick={() => scrollBy(-1)}
        >
          <i className="fa fa-chevron-left"></i>
        </button>

        <div className="guild-row-scroller" ref={scrollerRef} onScroll={onScroll}>
          {!visible || loading ? (
            <div className="guild-row-loading">
              <i className="fa fa-spinner fa-spin"></i> 加载中...
            </div>
          ) : error && items.length === 0 ? (
            <div className="guild-row-error" role="alert">
              <i className="fa fa-exclamation-circle"></i> 内容加载失败
              <button type="button" className="guild-row-retry" onClick={() => load(1, false)}>
                重试
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="guild-row-empty">暂无内容</div>
          ) : (
            <>
              {items.map((it) => (
                <div className="guild-row-card" key={`${it.type}-${it.id}`}>
                  {it.type === "article" ? (
                    <ArticleCard item={it} showSpace={false} />
                  ) : (
                    <PostCard post={feedItemToPost(it)} showSpace={false} />
                  )}
                </div>
              ))}
              {error && (
                <div className="guild-row-error is-tail" role="alert">
                  <button
                    type="button"
                    className="guild-row-retry"
                    onClick={() => load(pageRef.current + 1, true)}
                  >
                    加载失败，点击重试
                  </button>
                </div>
              )}
              {loadingMore && (
                <div className="guild-row-loading is-tail">
                  <i className="fa fa-spinner fa-spin"></i>
                </div>
              )}
            </>
          )}
        </div>

        <button
          type="button"
          className="guild-row-arrow"
          aria-label="向右滚动"
          disabled={(!canRight && !hasMore) || !visible}
          onClick={() => scrollBy(1)}
        >
          <i className="fa fa-chevron-right"></i>
        </button>
      </div>
    </section>
  );
}

/** 会馆广场：每个会馆一行（顶部栏 + 横向内容区）；保留会馆列表切换 */
export default function HuiGuanPage() {
  const router = useRouter();
  const [guilds, setGuilds] = useState<GuildListItem[] | null>(null);
  const [view, setView] = useState<"rows" | "list">("rows");
  const count = guilds?.length || 0;

  useEffect(() => {
    (async () => {
      try {
        const r = await guildApi.list();
        setGuilds([...(r.guilds || [])].sort((a, b) => a.id - b.id));
      } catch {
        setGuilds([]);
      }
    })();
  }, []);

  return (
    <div className="guild-page">
      <div className="guild-page-header">
        <h1 className="guild-page-title">会馆广场</h1>
        <p className="guild-page-subtitle">走进会馆，遇见同好</p>
        {count > 0 && (
          <button className="guild-view-toggle" type="button" onClick={() => setView(view === "rows" ? "list" : "rows")}>
            <i className={`fa ${view === "rows" ? "fa-list-ul" : "fa-th-large"}`}></i>
            {view === "rows" ? "查看所有会馆" : "返回会馆广场"}
          </button>
        )}
      </div>

      {guilds === null ? (
        <GlobalLoading />
      ) : count === 0 ? (
        <div className="guild-empty">
          <i className="fa fa-home"></i>
          <p className="guild-empty-title">还没有会馆</p>
          <p className="guild-empty-desc">会馆正在筹建中，先去论坛逛逛吧～</p>
          <Link className="guild-empty-link" href="/forum">
            前往论坛广场 <i className="fa fa-arrow-right"></i>
          </Link>
        </div>
      ) : view === "rows" ? (
        <div className="guild-rows">
          {guilds.map((g) => (
            <GuildFeedRow key={g.uuid || g.slug} guild={g} />
          ))}
        </div>
      ) : (
        <div className="guild-list">
          {guilds.map((g) => (
            <div className="guild-list-cell" key={g.uuid || g.slug}>
              <Link className="guild-list-item" href={`/huiguan/${g.slug}`}>
                <GuildLogo
                  logoFileId={g.logo_file_id}
                  guildUuid={g.uuid}
                  logoVersion={g.logo_version}
                  name={g.name}
                  hasLogo={g.has_logo}
                  color={g.theme_color}
                  size={48}
                  className="guild-logo guild-list-logo"
                />
                <div className="guild-list-body">
                  <div className="guild-list-name-row">
                    <span className="guild-list-name">{g.name}</span>
                    <span
                      className="guild-list-id"
                      style={{ background: themeColor(g.theme_color), color: contrastText(themeColor(g.theme_color)) }}
                    >
                      #{g.id}
                    </span>
                  </div>
                  <p className="guild-list-intro">{g.intro || "这个会馆还没有简介～"}</p>
                </div>
                <div className="guild-list-meta">
                  <span>
                    <i className="fa fa-user-o"></i> {g.leader?.name || "虚位以待"}
                  </span>
                  <span
                    className="guild-list-meta-link"
                    title="查看成员名单"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      router.push(`/huiguan/${g.slug}/members`);
                    }}
                  >
                    <i className="fa fa-users"></i> {g.member_count}
                  </span>
                </div>
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
