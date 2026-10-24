"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import AnnouncementBanner from "@/components/AnnouncementBanner";
import PostCard from "@/components/PostCard";
import { ListLoading, ListEmpty } from "@/components/ui/ListState";
import { postApi, Post } from "@/lib/api";

export default function HomePage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadRandom = useCallback(async (append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const r = await postApi.random();
      const list = r.posts || [];
      if (append) {
        // 随机接口可能重复返回同一批帖子：按 id 去重后追加
        setPosts((prev) => {
          const seen = new Set(prev.map((p) => p.id));
          return [...prev, ...list.filter((p) => !seen.has(p.id))];
        });
      } else {
        setPosts(list);
      }
    } catch {
      if (!append) setPosts([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    // 延后一个 tick 发起请求，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => loadRandom(), 0);
    return () => window.clearTimeout(t);
  }, [loadRandom]);

  return (
    <>
      {/* 首页公告：仅首页渲染，位于全局 Header 下方（跨页面布局不挂载） */}
      <AnnouncementBanner />
      <div className="home-container">
        <section className="home-quick-top">
          <Link className="quick-top-entry" href="/huiguan">
            <div className="quick-top-icon quick-top-icon-guild">
              <i className="fa fa-home"></i>
            </div>
            <div className="quick-top-body">
              <div className="quick-top-name">会馆广场</div>
              <div className="quick-top-desc">走进会馆，遇见同好</div>
            </div>
            <i className="fa fa-chevron-right quick-top-arrow"></i>
          </Link>
        </section>

        <section className="home-hero">
          <div className="home-hero-inner">
            <h1 className="home-hero-title">妖精论坛</h1>
            <p className="home-hero-subtitle">分享你的想法与故事</p>
            <div className="home-hero-actions">
              <Link href="/forum" className="home-hero-btn secondary">
                <i className="fa fa-list"></i> 论坛广场
              </Link>
            </div>
          </div>
        </section>

        <section className="home-feed">
          <div className="home-feed-header">
            <h2 className="home-feed-title">
              <i className="fa fa-random"></i> 随机推荐
              <span className="home-feed-tag" id="home-feed-tag">随机展示</span>
            </h2>
            <button className="home-refresh-btn" id="home-refresh-btn" onClick={() => loadRandom()}>
              <i className="fa fa-refresh"></i> 换一批
            </button>
          </div>

          <div className="home-post-list" id="home-post-list">
            {loading ? (
              <ListLoading />
            ) : posts.length === 0 ? (
              <ListEmpty />
            ) : (
              posts.map((p) => <PostCard key={p.id} post={p} />)
            )}
          </div>

          {/* 首页专属：底部「继续加载」按钮（不做滚动自动加载，避免无限请求） */}
          {!loading && posts.length > 0 && (
            <div className="home-load-more">
              <button
                type="button"
                className="home-load-more-btn"
                disabled={loadingMore}
                onClick={() => loadRandom(true)}
              >
                {loadingMore ? (
                  <>
                    <i className="fa fa-spinner fa-spin"></i> 加载中...
                  </>
                ) : (
                  <>
                    <i className="fa fa-refresh"></i> 继续加载
                  </>
                )}
              </button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
