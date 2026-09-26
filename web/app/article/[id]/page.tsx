"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import Markdown from "@/components/Markdown";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { guildApi, GuildArticle } from "@/lib/api";
import { formatTime, themeColor, themeTint } from "@/lib/constants";

type TocItem = { id: string; text: string; level: number };

/** 文章详情：元信息 + Markdown 正文 + 桌面端右侧章节导航（≥992px） */
export default function ArticlePage() {
  const { id } = useParams<{ id: string }>();
  // 按 id 记录加载结果：切换文章时旧数据自动失效（等 loading，无需在 effect 内重置）
  const [data, setData] = useState<{ id: string; article: GuildArticle | null; failed: boolean } | null>(null);
  const [toc, setToc] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    guildApi
      .article(id)
      .then((r) => {
        if (alive) setData({ id, article: r.article, failed: false });
      })
      .catch(() => {
        if (alive) setData({ id, article: null, failed: true });
      });
    return () => {
      alive = false;
    };
  }, [id]);

  const article = data && data.id === id ? data.article : null;
  const failed = !!(data && data.id === id && data.failed);

  // 从渲染后的正文中提取 h2/h3（补全唯一 id）作为章节列表
  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    const nodes = Array.from(root.querySelectorAll("h2, h3")) as HTMLElement[];
    const list = nodes.map((el, i) => {
      if (!el.id) el.id = `article-sec-${i}`;
      return { id: el.id, text: (el.textContent || "").trim(), level: el.tagName === "H2" ? 2 : 3 };
    });
    setToc(list);
  }, [article?.content]);

  // 滚动高亮当前章节
  useEffect(() => {
    if (toc.length === 0) return;
    let ticking = false;
    const compute = () => {
      ticking = false;
      const offset = 130;
      let cur = toc[0].id;
      for (const t of toc) {
        const el = document.getElementById(t.id);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= offset) cur = t.id;
        else break;
      }
      setActiveId(cur);
    };
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(compute);
    };
    compute();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [toc]);

  const jumpTo = (sid: string) => {
    const el = document.getElementById(sid);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(sid);
  };

  if (failed) {
    return (
      <div className="article-page">
        <div className="guild-empty">
          <i className="fa fa-book"></i>
          <p className="guild-empty-title">文章不存在</p>
          <Link className="guild-empty-link" href="/forum">
            前往论坛广场 <i className="fa fa-arrow-right"></i>
          </Link>
        </div>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="article-page">
        <GlobalLoading />
      </div>
    );
  }

  const theme = themeColor(article.guild_theme_color);

  return (
    <div className="article-page">
      <div className="article-layout">
        <div className="article-main">
          <h1 className="article-title">{article.title}</h1>

          <div className="article-meta">
            {article.guild_name && (
              <Link
                className="article-guild-tag"
                href={`/huiguan/${article.guild_slug}`}
                style={{ background: themeTint(theme), color: theme }}
              >
                <i className="fa fa-home"></i> {article.guild_name}
              </Link>
            )}
            {article.author && (
              <Link className="article-meta-item article-meta-author" href={`/users/${article.author.id}`}>
                <i className="fa fa-pencil"></i> {article.author.name}
              </Link>
            )}
            {article.participants.length > 0 && (
              <span className="article-meta-participants">
                <i className="fa fa-users"></i> 参与：
                {article.participants.map((p) => (
                  <Link key={p.user_id} className="article-participant" href={`/users/${p.user_id}`} title={p.user_name}>
                    <UserAvatar src={p.avatar} />
                    <span className="article-participant-name">{p.user_name}</span>
                  </Link>
                ))}
              </span>
            )}
            <span className="article-meta-item">
              <i className="fa fa-clock-o"></i> 创建 {formatTime(article.created_at)}
            </span>
            <span className="article-meta-item">
              <i className="fa fa-refresh"></i> 更新 {formatTime(article.updated_at)}
            </span>
            <span className="article-meta-item">
              <i className="fa fa-eye"></i> {article.views || 0}
            </span>
          </div>

          <div className="article-content" ref={bodyRef}>
            <Markdown content={article.content} className="post-body-html" />
          </div>
        </div>

        {/* 章节导航（窄屏隐藏） */}
        {toc.length > 0 && (
          <nav className="article-toc" aria-label="章节导航">
            <div className="article-toc-title">
              <i className="fa fa-list-ul"></i> 章节
            </div>
            <ul className="article-toc-list">
              {toc.map((t) => (
                <li key={t.id} className={t.level === 3 ? "toc-level-3" : undefined}>
                  <button
                    className={`article-toc-item ${activeId === t.id ? "active" : ""}`}
                    style={activeId === t.id ? { color: theme, borderColor: theme } : undefined}
                    onClick={() => jumpTo(t.id)}
                  >
                    {t.text}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </div>
    </div>
  );
}
