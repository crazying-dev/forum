"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import RichContent from "@/components/ui/RichContent";
import { guildApi, GuildIntroPageData } from "@/lib/api";
import { contrastText, formatUserTime, guildForeground, isLightHex, themeColor, themeInk, themeTint } from "@/lib/constants";
import { guildImageUrl } from "@/lib/media";

/** 会馆介绍页：封面/主题色 hero + 信息卡 + 富文本正文（管理端编辑的 HTML） */
export default function GuildIntroPage() {
  const { slug } = useParams<{ slug: string }>();
  // 按 slug 记录加载结果：切换会馆时旧数据自动失效
  const [data, setData] = useState<{ slug: string; page: GuildIntroPageData | null; failed: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    guildApi
      .intro(slug)
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
      <div className="guild-page guild-intro-page">
        <GlobalLoading />
      </div>
    );
  }

  // 会馆不存在或请求失败 → 空态 + 返回会馆页
  if (!page) {
    return (
      <div className="guild-page guild-intro-page">
        <div className="guild-empty">
          <i className="fa fa-home"></i>
          <p className="guild-empty-title">会馆不存在</p>
          <p className="guild-empty-desc">{failed ? "会馆介绍暂时无法加载" : "这个会馆不存在或已被解散"}</p>
          <Link className="guild-empty-link" href={`/huiguan/${encodeURIComponent(slug)}`}>
            返回会馆 <i className="fa fa-arrow-right"></i>
          </Link>
        </div>
      </div>
    );
  }

  const g = page.guild;
  const theme = themeColor(g.theme_color);
  // 卡片底上的主题色文字/图标：日间用可读 ink，夜间由 .theme-ink 规则提亮
  const inkStyle = { "--guild-ink": themeInk(theme) } as React.CSSProperties;
  const lightTheme = isLightHex(theme);
  // 封面图（媒体直出 /ov2/api/media/<id>）；旧 GridFS 文件或未设封面时回退主题色渐变
  const coverUrl = guildImageUrl(g.cover_file_id, g.uuid, "intro-images");
  const hasCover = !!coverUrl;
  // hero 前景色：有封面统一白字 + 层级遮罩；否则亮色主题用深字、暗色主题用白字
  const heroVars = {
    "--guild-fg": hasCover ? "#ffffff" : guildForeground(theme),
    "--guild-fg-soft": hasCover
      ? "rgba(255, 255, 255, 0.18)"
      : lightTheme
        ? "rgba(23, 50, 58, 0.10)"
        : "rgba(255, 255, 255, 0.18)",
    "--guild-shade": hasCover
      ? "linear-gradient(180deg, rgba(8, 20, 26, 0.18) 0%, rgba(8, 20, 26, 0.62) 100%)"
      : lightTheme
        ? "linear-gradient(135deg, rgba(255, 255, 255, 0) 32%, rgba(255, 255, 255, 0.42) 100%)"
        : "linear-gradient(135deg, rgba(0, 0, 0, 0) 32%, rgba(0, 0, 0, 0.28) 100%)",
    "--guild-ts": hasCover || !lightTheme ? "0 1px 2px rgba(0, 0, 0, 0.28)" : "none",
  } as React.CSSProperties;
  const heroStyle: React.CSSProperties = hasCover
    ? { backgroundImage: `url(${coverUrl})`, backgroundSize: "cover", backgroundPosition: "center", ...heroVars }
    : { background: `linear-gradient(135deg, ${theme} 0%, ${themeTint(theme, "cc")} 100%)`, ...heroVars };

  return (
    <div
      className="guild-page guild-intro-page"
      style={{ background: `linear-gradient(180deg, ${themeTint(theme, "26")} 0%, transparent 420px)` }}
    >
      {/* hero：徽标 + 名称 + 一句话简介 */}
      <div className="guild-intro-hero" style={heroStyle}>
        <div className="guild-hero-shade"></div>
        <div className="guild-intro-hero-body">
          <p className="guild-intro-hero-guild">
            <i className="fa fa-home"></i> 会馆介绍
          </p>
          <span className="guild-intro-badge" style={{ background: hasCover ? "rgba(255, 255, 255, 0.18)" : "var(--guild-fg-soft)" }}>
            <i className="fa fa-building-o"></i>
          </span>
          <h1 className="guild-intro-hero-name">{g.name}</h1>
          <p className="guild-intro-hero-intro">{g.intro || "这个会馆还没有简介～"}</p>
        </div>
      </div>

      {/* 信息卡：成立时间 / 成员数 / 分类数 */}
      <div className="guild-intro-meta-card">
        <div className="guild-intro-meta-item">
          <i className="fa fa-clock-o"></i>
          <span className="guild-intro-meta-label">成立时间</span>
          <span className="guild-intro-meta-value">{g.created_at ? formatUserTime(g.created_at) : "—"}</span>
        </div>
        <Link className="guild-intro-meta-item guild-intro-meta-link" href={`/huiguan/${encodeURIComponent(g.slug)}/members`}>
          <i className="fa fa-users"></i>
          <span className="guild-intro-meta-label">成员</span>
          <span className="guild-intro-meta-value">
            {g.member_count} 人 <i className="fa fa-arrow-right"></i>
          </span>
        </Link>
        <div className="guild-intro-meta-item">
          <i className="fa fa-tags"></i>
          <span className="guild-intro-meta-label">分类</span>
          <span className="guild-intro-meta-value">{g.category_count} 个</span>
        </div>
      </div>

      {/* 正文（管理端编辑的 HTML） */}
      <section className="guild-intro-panel">
        <h2 className="guild-intro-panel-title theme-ink" style={inkStyle}>
          <i className="fa fa-star"></i> 会馆介绍
        </h2>
        {page.content ? (
          <RichContent content={page.content} className="guild-intro-content" />
        ) : (
          <p className="guild-intro-placeholder">这个会馆还没有填写介绍～</p>
        )}
      </section>

      <div className="guild-intro-actions">
        <Link
          className="guild-intro-back-btn"
          href={`/huiguan/${encodeURIComponent(g.slug)}`}
          style={{ background: theme, color: contrastText(theme) }}
        >
          <i className="fa fa-arrow-left"></i> 返回会馆
        </Link>
      </div>
    </div>
  );
}
