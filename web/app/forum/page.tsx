"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ArticleCard from "@/components/ArticleCard";
import PostCard from "@/components/PostCard";
import { ListEmpty, ListLoading, LoadMoreButton } from "@/components/ui/ListState";
import { feedApi, guildApi, FeedItem, GuildCategory, GuildListItem } from "@/lib/api";
import { POST_CATEGORIES } from "@/lib/constants";
import { feedItemToPost } from "@/lib/feed";

// 空间：全部 / 公共空间 / 指定会馆
type Space = "all" | "public" | "guild";

/** 论坛页：空间 + 分类筛选，帖子与文章混合信息流 */
export default function ForumPage() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [space, setSpace] = useState<Space>("all");
  const [guildId, setGuildId] = useState<number | null>(null);
  const [guildName, setGuildName] = useState("");
  const [guildCategories, setGuildCategories] = useState<GuildCategory[]>([]);
  const [guilds, setGuilds] = useState<GuildListItem[]>([]);
  const [category, setCategory] = useState("");
  const [dropOpen, setDropOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);
  const dropRef = useRef<HTMLDivElement>(null);

  // 会馆列表（下拉选项）
  useEffect(() => {
    guildApi
      .list()
      .then((r) => setGuilds([...(r.guilds || [])].sort((a, b) => a.id - b.id)))
      .catch(() => setGuilds([]));
  }, []);

  // 点击空白关闭会馆下拉
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setDropOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const load = useCallback(
    async (pageNo: number, append: boolean) => {
      try {
        const r = await feedApi.list(space, space === "guild" ? guildId || 0 : 0, category, pageNo, 20);
        setItems((prev) => (append ? [...prev, ...(r.items || [])] : r.items || []));
        setHasMore(!!r.has_more);
      } catch {
        if (!append) setItems([]);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [space, guildId, category]
  );

  useEffect(() => {
    pageRef.current = 1;
    // 延后一个 tick 发起请求，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => load(1, false), 0);
    return () => window.clearTimeout(t);
  }, [load]);

  const loadMore = () => {
    pageRef.current += 1;
    setLoadingMore(true);
    load(pageRef.current, true);
  };

  const selectSpace = (s: Space) => {
    setSpace(s);
    setCategory("");
    setDropOpen(false);
    if (s !== "guild") setGuildId(null);
    setLoading(true);
  };

  const selectGuild = async (g: GuildListItem) => {
    setGuildId(g.id);
    setGuildName(g.name);
    setSpace("guild");
    setCategory("");
    setDropOpen(false);
    setLoading(true);
    try {
      const r = await guildApi.detail(g.slug);
      setGuildCategories(r.guild.categories || []);
    } catch {
      setGuildCategories([]);
    }
  };

  // 分类 chips：公共空间用公共分类常量；会馆用该馆自定义分类（无则隐藏）
  const chips: { key: string; label: string }[] =
    space === "public"
      ? [{ key: "", label: "全部" }, ...POST_CATEGORIES]
      : space === "guild"
        ? [{ key: "", label: "全部" }, ...guildCategories.map((c) => ({ key: c.name, label: c.name }))]
        : [];

  return (
    <>
      <div className="forum-container">
        <div className="forum-header">
          <h1 className="forum-title">妖精论坛</h1>
          <p className="forum-subtitle">分享你的想法与故事</p>
          <Link href="/post/create" className="forum-create-btn">
            <i className="fa fa-pencil"></i> 发布帖子
          </Link>
        </div>

        <div className="forum-filters">
          <div className="forum-filter-row">
            <span className="forum-filter-label">空间</span>
            <button className={`forum-tab ${space === "all" ? "active" : ""}`} onClick={() => selectSpace("all")}>
              全部
            </button>
            <button className={`forum-tab ${space === "public" ? "active" : ""}`} onClick={() => selectSpace("public")}>
              公共空间
            </button>
            <div className="forum-guild-select" ref={dropRef}>
              <button
                className={`forum-tab forum-guild-toggle ${space === "guild" ? "active" : ""}`}
                onClick={() => setDropOpen((o) => !o)}
                aria-haspopup="listbox"
                aria-expanded={dropOpen}
              >
                <i className="fa fa-home"></i>
                <span className="forum-guild-toggle-text">{space === "guild" && guildName ? guildName : "会馆"}</span>
                <i className={`fa ${dropOpen ? "fa-caret-up" : "fa-caret-down"}`}></i>
              </button>
              {dropOpen && (
                <div className="forum-guild-dropdown" role="listbox">
                  <div className="forum-guild-dropdown-title">选择会馆</div>
                  {guilds.length === 0 ? (
                    <div className="forum-guild-dropdown-empty">暂无会馆</div>
                  ) : (
                    guilds.map((g) => (
                      <button
                        key={g.id}
                        className={`forum-guild-option ${guildId === g.id ? "active" : ""}`}
                        onClick={() => selectGuild(g)}
                      >
                        <span className="forum-guild-option-name">{g.name}</span>
                        <span className="forum-guild-option-id">#{g.id}</span>
                        <span className="forum-guild-option-count">{g.member_count} 人</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {space !== "all" && chips.length > 1 && (
            <div className="forum-filter-row forum-category-row">
              <span className="forum-filter-label">分类</span>
              {chips.map((c) => (
                <button
                  key={c.key}
                  className={`forum-tab ${category === c.key ? "active" : ""}`}
                  data-category={c.key}
                  onClick={() => {
                    if (category !== c.key) setLoading(true);
                    setCategory(c.key);
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="forum-post-list" id="forum-post-list">
          {loading ? (
            <ListLoading />
          ) : items.length === 0 ? (
            <ListEmpty text="暂无内容" />
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

        {hasMore && <LoadMoreButton loading={loadingMore} onClick={loadMore} id="forum-load-more" />}
      </div>
    </>
  );
}
