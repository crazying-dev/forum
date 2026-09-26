"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import GuildLogo from "@/components/ui/GuildLogo";
import { guildApi, GuildListItem } from "@/lib/api";
import { formatUserTime, themeColor, themeTint } from "@/lib/constants";
import { useCarousel } from "@/lib/useCarousel";

/** 会馆广场：轮播主视图 + 紧凑列表切换 */
export default function HuiGuanPage() {
  const router = useRouter();
  const [guilds, setGuilds] = useState<GuildListItem[] | null>(null);
  const [view, setView] = useState<"carousel" | "list">("carousel");
  const count = guilds?.length || 0;
  const { index, go, jump, hoverProps } = useCarousel(count);
  const current = guilds && count > 0 ? guilds[index] : null;

  useEffect(() => {
    (async () => {
      try {
        const r = await guildApi.list();
        // 按 id 升序（后端已排序，此处兜底）
        setGuilds([...(r.guilds || [])].sort((a, b) => a.id - b.id));
      } catch {
        setGuilds([]);
      }
    })();
  }, []);

  const prev = guilds && count > 1 ? guilds[(index - 1 + count) % count] : null;
  const next = guilds && count > 1 ? guilds[(index + 1) % count] : null;

  return (
    <div className="guild-page">
      <div className="guild-page-header">
        <h1 className="guild-page-title">会馆广场</h1>
        <p className="guild-page-subtitle">走进会馆，遇见同好</p>
        {count > 0 && (
          <button className="guild-view-toggle" onClick={() => setView(view === "carousel" ? "list" : "carousel")}>
            <i className={`fa ${view === "carousel" ? "fa-list-ul" : "fa-picture-o"}`}></i>
            {view === "carousel" ? "查看所有会馆" : "返回轮播"}
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
      ) : view === "carousel" && current ? (
        <div className="guild-carousel" {...hoverProps}>
          <div className="guild-carousel-stage">
            {prev && (
              <button className="guild-carousel-thumb thumb-prev" onClick={() => go(-1)} title={`切换到 ${prev.name}`}>
                <GuildLogo
                  id={prev.id}
                  name={prev.name}
                  hasLogo={prev.has_logo}
                  logoVersion={prev.logo_version}
                  color={prev.theme_color}
                  size={44}
                  className="guild-logo guild-thumb-logo"
                />
                <span className="guild-thumb-name">{prev.name}</span>
              </button>
            )}

            <button className="guild-carousel-arrow arrow-left" aria-label="上一个会馆" onClick={() => go(-1)}>
              <i className="fa fa-chevron-left"></i>
            </button>

            <div
              className="guild-carousel-card"
              onClick={() => router.push(`/huiguan/${current.slug}`)}
              style={{ borderColor: themeTint(current.theme_color, "55") }}
            >
              <div className="guild-card-glow" style={{ background: `linear-gradient(135deg, ${themeTint(current.theme_color, "44")} 0%, transparent 72%)` }}></div>
              <GuildLogo
                id={current.id}
                name={current.name}
                hasLogo={current.has_logo}
                logoVersion={current.logo_version}
                color={current.theme_color}
                size={96}
                className="guild-logo guild-card-logo"
              />
              <div className="guild-card-body">
                <div className="guild-card-name-row">
                  <span className="guild-card-name">{current.name}</span>
                  <span className="guild-card-id" style={{ background: themeTint(current.theme_color), color: themeColor(current.theme_color) }}>
                    #{current.id}
                  </span>
                </div>
                <p className="guild-card-intro">{current.intro || "这个会馆还没有简介～"}</p>
                <div className="guild-card-meta">
                  <span className="guild-card-meta-item">
                    <i className="fa fa-user-o"></i> 馆长：{current.leader?.name || "虚位以待"}
                  </span>
                  <span className="guild-card-meta-item">
                    <i className="fa fa-users"></i> {current.member_count} 人
                  </span>
                  <span className="guild-card-meta-item">
                    <i className="fa fa-clock-o"></i> 创建于 {current.created_at ? formatUserTime(current.created_at) : "—"}
                  </span>
                </div>
              </div>
              <Link
                className="guild-enter-btn"
                href={`/huiguan/${current.slug}`}
                onClick={(e) => e.stopPropagation()}
                style={{ background: themeColor(current.theme_color) }}
              >
                进入会馆 <i className="fa fa-arrow-right"></i>
              </Link>
            </div>

            <button className="guild-carousel-arrow arrow-right" aria-label="下一个会馆" onClick={() => go(1)}>
              <i className="fa fa-chevron-right"></i>
            </button>

            {next && (
              <button className="guild-carousel-thumb thumb-next" onClick={() => go(1)} title={`切换到 ${next.name}`}>
                <GuildLogo
                  id={next.id}
                  name={next.name}
                  hasLogo={next.has_logo}
                  logoVersion={next.logo_version}
                  color={next.theme_color}
                  size={44}
                  className="guild-logo guild-thumb-logo"
                />
                <span className="guild-thumb-name">{next.name}</span>
              </button>
            )}
          </div>

          <div className="guild-carousel-dots">
            {guilds.map((g, i) => (
              <button
                key={g.id}
                className={`guild-carousel-dot ${i === index ? "active" : ""}`}
                aria-label={`切换到 ${g.name}`}
                onClick={() => jump(i)}
                style={i === index ? { background: themeColor(g.theme_color) } : undefined}
              ></button>
            ))}
          </div>
        </div>
      ) : (
        <div className="guild-list">
          {guilds.map((g) => (
            <Link key={g.id} className="guild-list-item" href={`/huiguan/${g.slug}`}>
              <GuildLogo
                id={g.id}
                name={g.name}
                hasLogo={g.has_logo}
                logoVersion={g.logo_version}
                color={g.theme_color}
                size={48}
                className="guild-logo guild-list-logo"
              />
              <div className="guild-list-body">
                <div className="guild-list-name-row">
                  <span className="guild-list-name">{g.name}</span>
                  <span className="guild-list-id" style={{ background: themeTint(g.theme_color), color: themeColor(g.theme_color) }}>
                    #{g.id}
                  </span>
                </div>
                <p className="guild-list-intro">{g.intro || "这个会馆还没有简介～"}</p>
              </div>
              <div className="guild-list-meta">
                <span>
                  <i className="fa fa-user-o"></i> {g.leader?.name || "虚位以待"}
                </span>
                <span>
                  <i className="fa fa-users"></i> {g.member_count}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
