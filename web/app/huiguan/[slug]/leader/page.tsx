"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import RichContent from "@/components/ui/RichContent";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { guildApi, GuildLeaderPageData } from "@/lib/api";
import { contrastText, guildForeground, isLightHex, themeColor, themeInk, themeTint } from "@/lib/constants";

/** 馆长介绍页：主题色渐变头部 + 寄语 + 正文（管理端 HTML） */
export default function GuildLeaderPage() {
  const { slug } = useParams<{ slug: string }>();
  // 按 slug 记录加载结果：切换会馆时旧数据自动失效
  const [data, setData] = useState<{ slug: string; page: GuildLeaderPageData | null; failed: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    guildApi
      .leaderPage(slug)
      .then((r) => {
        if (alive) setData({ slug, page: r, failed: false });
      })
      .catch(() => {
        if (alive) setData({ slug, page: null, failed: true });
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  const page = data && data.slug === slug ? data.page : null;
  const failed = !!(data && data.slug === slug && data.failed);

  // 加载中（含切换会馆时旧数据失效）
  if (!data || data.slug !== slug) {
    return (
      <div className="guild-page guild-leader-page">
        <GlobalLoading />
      </div>
    );
  }

  // 无馆长（或请求失败）→ 空态 + 返回会馆页
  if (!page || !page.leader) {
    return (
      <div className="guild-page guild-leader-page">
        <div className="guild-empty">
          <i className="fa fa-user-o"></i>
          <p className="guild-empty-title">馆长虚位以待</p>
          <p className="guild-empty-desc">{failed ? "馆长介绍暂时无法加载" : "这个会馆还没有馆长"}</p>
          <Link className="guild-empty-link" href={`/huiguan/${slug}`}>
            返回会馆 <i className="fa fa-arrow-right"></i>
          </Link>
        </div>
      </div>
    );
  }

  const { guild, leader } = page;
  const theme = themeColor(guild.theme_color);
  // 卡片底上的主题色文字/图标：日间用可读 ink，夜间由 .theme-ink 规则提亮
  const inkStyle = { "--guild-ink": themeInk(theme) } as React.CSSProperties;
  // hero 前景色：亮色主题用深字，暗色主题用白字
  const fg = guildForeground(theme);
  const lightTheme = isLightHex(theme);
  const heroVars = {
    "--guild-fg": fg,
    "--guild-fg-soft": lightTheme ? "rgba(23, 50, 58, 0.10)" : "rgba(255, 255, 255, 0.18)",
    "--guild-shade": lightTheme
      ? "linear-gradient(135deg, rgba(255, 255, 255, 0) 32%, rgba(255, 255, 255, 0.42) 100%)"
      : "linear-gradient(135deg, rgba(0, 0, 0, 0) 32%, rgba(0, 0, 0, 0.28) 100%)",
    "--guild-ts": lightTheme ? "none" : "0 1px 2px rgba(0, 0, 0, 0.28)",
  } as React.CSSProperties;

  return (
    <div
      className="guild-page guild-leader-page"
      style={{ background: `linear-gradient(180deg, ${themeTint(theme, "26")} 0%, transparent 420px)` }}
    >
      {/* 主题色渐变头部 + 资料头 */}
      <div className="guild-leader-hero" style={{ background: `linear-gradient(135deg, ${theme} 0%, ${themeTint(theme, "cc")} 100%)`, ...heroVars }}>
        <div className="guild-hero-shade"></div>
        <div className="guild-leader-hero-body">
          <p className="guild-leader-hero-guild">
            <i className="fa fa-home"></i> {guild.name}
          </p>
          <div className="guild-leader-hero-avatar">
            <UserAvatar
              src={leader.avatar}
              alt={leader.name}
              fallbackClassName="avatar-fallback avatar-fallback-lg"
              userId={leader.id}
            />
          </div>
          <div className="guild-leader-hero-name-row">
            <h1 className="guild-leader-hero-name">{leader.name}</h1>
            {leader.title ? <span className="guild-leader-hero-title">{leader.title}</span> : null}
            <span className="guild-leader-hero-tag">
              <i className="fa fa-crown"></i> 馆长
            </span>
          </div>
          <p className="guild-leader-hero-intro">{leader.intro || "这位馆长很低调～"}</p>
        </div>
      </div>

      {/* 寄语（短引用样式） */}
      <section className="guild-leader-panel">
        <h2 className="guild-leader-panel-title theme-ink" style={inkStyle}>
          <i className="fa fa-quote-left"></i> 馆长寄语
        </h2>
        {page.leader_bio ? (
          <blockquote className="guild-leader-quote">{page.leader_bio}</blockquote>
        ) : (
          <p className="guild-leader-placeholder">馆长还没有留下寄语～</p>
        )}
      </section>

      {/* 正文（管理端编辑的 HTML） */}
      <section className="guild-leader-panel">
        <h2 className="guild-leader-panel-title theme-ink" style={inkStyle}>
          <i className="fa fa-star"></i> 馆长介绍
        </h2>
        {page.content ? (
          <RichContent content={page.content} className="guild-leader-content" />
        ) : (
          <p className="guild-leader-placeholder">馆长还没有填写介绍～</p>
        )}
      </section>

      <div className="guild-leader-actions">
        <Link
          className="guild-leader-profile-btn"
          href={`/users/${leader.id}`}
          style={{ background: theme, color: contrastText(theme) }}
        >
          访问完整个人主页 <i className="fa fa-arrow-right"></i>
        </Link>
      </div>
    </div>
  );
}
