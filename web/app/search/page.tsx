"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { useEffect, useState } from "react";
import PostCard from "@/components/PostCard";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ListLoading, ListEmpty, LoadMoreButton } from "@/components/ui/ListState";
import { guildApi, miscApi, ArticleSearchItem, Post, UserBrief } from "@/lib/api";
import { timeAgo } from "@/lib/constants";

function SearchInner() {
  const params = useSearchParams();
  const router = useRouter();
  // 已提交（URL 中）的搜索词：文章结果以它为准（输入框实时值不触发请求）
  const urlKw = (params.get("k") || "").trim();
  const [kw, setKw] = useState("");
  const [tab, setTab] = useState<"posts" | "users" | "articles">("posts");
  const [posts, setPosts] = useState<Post[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [articles, setArticles] = useState<ArticleSearchItem[]>([]);
  const [postsMore, setPostsMore] = useState(false);
  const [usersMore, setUsersMore] = useState(false);
  const [articlesMore, setArticlesMore] = useState(false);
  // 已加载文章结果对应的关键词（文章 Tab 懒加载，切换关键词时重新拉取）
  const [articleKw, setArticleKw] = useState("");
  const [searching, setSearching] = useState(false);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const doSearch = async (k: string, page = 1, append = false) => {
    setSearching(true);
    setSearched(true);
    try {
      const r = await miscApi.search(k, "both", page, 20);
      if (append) {
        setPosts((p) => [...p, ...(r.posts || [])]);
      } else {
        setPosts(r.posts || []);
        setUsers(r.users || []);
      }
      setPostsMore(!!r.posts_has_more);
      setUsersMore(!!r.users_has_more);
    } catch {
      if (!append) { setPosts([]); setUsers([]); }
    } finally {
      setSearching(false);
    }
  };

  // 文章搜索（服务端要求 k≥2）；结果独立存储，与帖子/用户互不影响
  const searchArticles = async (k: string, page = 1, append = false) => {
    if (k.length < 2) return;
    setSearching(true);
    setArticlesLoading(true);
    try {
      const r = await guildApi.searchArticles(k, page, 20);
      const list = r.articles || [];
      setArticles((prev) => (append ? [...prev, ...list] : list));
      setArticlesMore(!!r.has_more);
    } catch {
      if (!append) {
        setArticles([]);
        setArticlesMore(false);
      }
    } finally {
      setArticleKw(k);
      setArticlesLoading(false);
      setSearching(false);
    }
  };

  useEffect(() => {
    const k = params.get("k");
    if (k) {
      setKw(k);
      doSearch(k, 1, false);
      // 关键词变化：文章结果失效，切到文章 Tab 时再按需加载
      setArticles([]);
      setArticlesMore(false);
      setArticleKw("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // 文章 Tab：首次进入（或关键词变化后进入）时惰性加载（延后一个 tick，避免在 effect 内同步触发加载态）
  useEffect(() => {
    if (tab !== "articles" || urlKw.length < 2 || articleKw === urlKw) return;
    const t = window.setTimeout(() => searchArticles(urlKw, 1, false), 0);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, urlKw]);

  // 动态标签页标题：与 URL 中的搜索关键词联动（基础标题由 app/search/layout.tsx 提供）
  useEffect(() => {
    const k = params.get("k");
    document.title = k ? `妖精论坛 - 搜索：${k}` : "妖精论坛 - 搜索";
  }, [params]);

  const submit = () => {
    const k = kw.trim();
    // 帖子/用户搜索最少 1 个字符（文章搜索结果页内要求 ≥2，见 searchArticles）
    if (k.length < 1) return;
    router.push(`/search?k=${encodeURIComponent(k)}`);
  };

  const loadMore = () => {
    if (tab === "articles") {
      const page = Math.ceil(articles.length / 20) + 1;
      searchArticles(urlKw, page, true);
      return;
    }
    const page = tab === "posts" ? Math.ceil(posts.length / 20) + 1 : Math.ceil(users.length / 20) + 1;
    doSearch(kw, page, true);
  };

  return (
    <div className="forum-container">
      <div className="forum-header">
        <h1 className="forum-title">搜索</h1>
      </div>

      <div className="search-page-form">
        <div className="search-page-input-wrapper">
          <input
            type="text"
            id="search-page-input"
            className="search-page-input"
            placeholder="输入搜索关键词..."
            autoComplete="off"
            value={kw}
            onChange={(e) => setKw(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <button id="search-page-btn" className="search-page-btn" onClick={submit}>
            <i className="fa fa-search"></i> 搜索
          </button>
        </div>
      </div>

      {searched && (
        <div id="search-page-results">
          <div className="forum-header" style={{ paddingTop: 0 }}>
            <p className="forum-subtitle" id="search-subtitle">{searching ? "正在搜索..." : `「${kw}」的搜索结果`}</p>
          </div>

          <div className="search-tabs" id="search-tabs">
            <button className={`search-tab ${tab === "posts" ? "active" : ""}`} data-tab="posts" onClick={() => setTab("posts")}>帖子</button>
            <button className={`search-tab ${tab === "users" ? "active" : ""}`} data-tab="users" onClick={() => setTab("users")}>用户</button>
            <button className={`search-tab ${tab === "articles" ? "active" : ""}`} data-tab="articles" onClick={() => setTab("articles")}>文章</button>
          </div>

          <div className="forum-post-list" id="search-post-list" style={{ display: tab === "posts" ? "block" : "none" }}>
            {searching && posts.length === 0 ? (
              <ListLoading />
            ) : posts.length === 0 ? (
              <ListEmpty text="未找到相关帖子" />
            ) : (
              posts.map((p) => <PostCard key={p.id} post={p} />)
            )}
          </div>

          <div className="forum-user-list" id="search-user-list" style={{ display: tab === "users" ? "block" : "none" }}>
            {searching && users.length === 0 ? (
              <ListLoading />
            ) : users.length === 0 ? (
              <ListEmpty text="未找到相关用户" />
            ) : (
              users.map((u) => (
                <Link className="search-user-item" href={`/users/${u.id}`} key={u.id} style={{ display: "flex" }}>
                  <div className="search-user-avatar-wrapper">
                    <UserAvatar
                      src={u.avatar}
                      alt={u.name}
                      imgClassName="search-user-avatar"
                      fallbackClassName="avatar-fallback search-user-avatar-fallback"
                      userId={u.id}
                    />
                  </div>
                  <div className="search-user-info">
                    <div className="search-user-name" style={{ whiteSpace: "nowrap" }}>{u.name}</div>
                    <div className="search-user-time">注册于 未知</div>
                  </div>
                </Link>
              ))
            )}
          </div>

          <div className="search-article-list" id="search-article-list" style={{ display: tab === "articles" ? "flex" : "none" }}>
            {urlKw.length < 2 ? (
              <ListEmpty text="文章搜索请至少输入 2 个字符" />
            ) : articlesLoading || articleKw !== urlKw ? (
              <ListLoading />
            ) : articles.length === 0 ? (
              <ListEmpty text="未找到相关文章" />
            ) : (
              articles.map((a) => (
                <Link className="search-article-item" href={`/article/${encodeURIComponent(a.id)}`} key={a.id}>
                  <div className="search-article-icon"><i className="fa fa-book"></i></div>
                  <div className="search-article-info">
                    <div className="search-article-title">{a.title || "无标题"}</div>
                    <div className="search-article-meta">
                      {a.guild_name && (
                        <span className="search-article-guild"><i className="fa fa-home"></i> {a.guild_name}</span>
                      )}
                      {a.created_at && <span className="search-article-time">{timeAgo(a.created_at)}</span>}
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>

          {(tab === "posts" ? postsMore : tab === "users" ? usersMore : articlesMore) && (
            <LoadMoreButton loading={searching} onClick={loadMore} id="search-load-more" />
          )}
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <>
      <Suspense fallback={<div style={{ textAlign: "center", padding: 40 }}>加载中...</div>}>
        <SearchInner />
      </Suspense>
    </>
  );
}
