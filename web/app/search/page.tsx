"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { useEffect, useState } from "react";
import PostCard from "@/components/PostCard";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ListLoading, ListEmpty, LoadMoreButton } from "@/components/ui/ListState";
import { miscApi, Post, UserBrief } from "@/lib/api";
import { isVip } from "@/lib/constants";

function SearchInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [kw, setKw] = useState("");
  const [tab, setTab] = useState<"posts" | "users">("posts");
  const [posts, setPosts] = useState<Post[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [postsMore, setPostsMore] = useState(false);
  const [usersMore, setUsersMore] = useState(false);
  const [searching, setSearching] = useState(false);
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

  useEffect(() => {
    const k = params.get("k");
    if (k) {
      setKw(k);
      doSearch(k, 1, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // 动态标签页标题：与 URL 中的搜索关键词联动（基础标题由 app/search/layout.tsx 提供）
  useEffect(() => {
    const k = params.get("k");
    document.title = k ? `妖精论坛 - 搜索：${k}` : "妖精论坛 - 搜索";
  }, [params]);

  const submit = () => {
    const k = kw.trim();
    if (k.length < 2) return;
    router.push(`/search?k=${encodeURIComponent(k)}`);
  };

  const loadMore = () => {
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

          <div className="forum-user-list" id="search-user-list">
            {searching && users.length === 0 ? (
              <ListLoading />
            ) : users.length === 0 ? (
              <ListEmpty text="未找到相关用户" />
            ) : (
              <div style={{ display: tab === "users" ? "block" : "none" }}>
                {users.map((u) => {
                  // VIP 图标（内置 vip.svg）与前缀徽标统一在头像右下角：VIP 优先靠角，徽标向左并排
                  const vip = isVip(u.vip);
                  return (
                    <Link className="search-user-item" href={`/users/${u.id}`} key={u.id} style={{ display: "flex" }}>
                      <div className="search-user-avatar-wrapper">
                        <UserAvatar
                          src={u.avatar}
                          alt={u.name}
                          imgClassName="search-user-avatar"
                          fallbackClassName="avatar-fallback search-user-avatar-fallback"
                          userId={u.id}
                          vip={vip}
                        />
                      </div>
                      <div className="search-user-info">
                        <div className="search-user-name" style={{ whiteSpace: "nowrap" }}>{u.name}</div>
                        <div className="search-user-time">注册于 未知</div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {(tab === "posts" ? postsMore : usersMore) && (
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
