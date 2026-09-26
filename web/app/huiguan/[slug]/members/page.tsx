"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import BackButton from "@/components/ui/BackButton";
import { ListEmpty, ListLoading, LoadMoreButton } from "@/components/ui/ListState";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { guildApi, GuildDetail, GuildMember } from "@/lib/api";
import { contrastText, isVip, themeColor, themeInk, themeTint } from "@/lib/constants";

/** 会馆成员名单：馆长特写卡 + 成员网格（分页加载） */
export default function GuildMembersPage() {
  const { slug } = useParams<{ slug: string }>();
  // 按 slug 记录加载结果：切换会馆时旧数据自动失效
  const [guildData, setGuildData] = useState<{ slug: string; guild: GuildDetail | null } | null>(null);
  const [listData, setListData] = useState<{ slug: string; members: GuildMember[]; hasMore: boolean } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageRef = useRef(1);

  // 会馆详情（名称/成员数/馆长）
  useEffect(() => {
    let alive = true;
    guildApi
      .detail(slug)
      .then((r) => {
        if (alive) setGuildData({ slug, guild: r.guild });
      })
      .catch(() => {
        if (alive) setGuildData({ slug, guild: null });
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  const loadMembers = useCallback(
    async (pageNo: number, append: boolean) => {
      try {
        const r = await guildApi.members(slug, pageNo, 24);
        setListData((prev) => {
          const base = prev && prev.slug === slug ? prev : { slug, members: [] as GuildMember[], hasMore: false };
          return {
            slug,
            members: append ? [...base.members, ...(r.members || [])] : r.members || [],
            hasMore: !!r.has_more,
          };
        });
      } catch {
        setListData((prev) =>
          prev && prev.slug === slug
            ? { ...prev, members: append ? prev.members : [], hasMore: false }
            : { slug, members: [], hasMore: false }
        );
      } finally {
        setLoadingMore(false);
      }
    },
    [slug]
  );

  useEffect(() => {
    pageRef.current = 1;
    // 延后一个 tick 发起请求，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => loadMembers(1, false), 0);
    return () => window.clearTimeout(t);
  }, [loadMembers]);

  const loadMore = () => {
    pageRef.current += 1;
    setLoadingMore(true);
    loadMembers(pageRef.current, true);
  };

  const guild = guildData && guildData.slug === slug ? guildData.guild : null;
  const members = listData && listData.slug === slug ? listData.members : [];
  const hasMore = !!(listData && listData.slug === slug && listData.hasMore);
  const loading = !listData || listData.slug !== slug;
  // 馆长特写已单独展示，网格中跳过
  const gridMembers = members.filter((m) => !m.is_leader);

  const theme = themeColor(guild?.theme_color);
  const inkStyle = { "--guild-ink": themeInk(theme) } as React.CSSProperties;

  return (
    <div
      className="guild-page guild-members-page"
      style={{ background: guild ? `linear-gradient(180deg, ${themeTint(theme, "26")} 0%, transparent 340px)` : undefined }}
    >
      <BackButton />

      <div className="guild-members-header">
        <h1 className="guild-members-title">
          <i className="fa fa-users"></i> 会馆成员{guild ? ` · 共 ${guild.member_count} 人` : ""}
        </h1>
      </div>

      {/* 馆长特写（居中，整卡跳转个人主页） */}
      {guild?.leader && (
        <Link
          className="guild-members-leader"
          href={`/users/${guild.leader.id}`}
          style={{ borderColor: themeTint(theme, "55") }}
        >
          <div className="guild-members-leader-avatar">
            <UserAvatar
              src={guild.leader.avatar}
              alt={guild.leader.name}
              fallbackClassName="avatar-fallback avatar-fallback-lg"
              userId={guild.leader.id}
            />
          </div>
          <div className="guild-members-leader-name-row">
            <span className="guild-members-leader-name Username">{guild.leader.name}</span>
            {guild.leader.title ? (
              <span className="guild-leader-title theme-ink" style={inkStyle}>
                {guild.leader.title}
              </span>
            ) : null}
            <span className="guild-leader-tag" style={{ background: theme, color: contrastText(theme) }}>
              <i className="fa fa-crown"></i> 馆长
            </span>
          </div>
          <p className="guild-members-leader-intro">{guild.leader.intro || "这位馆长很低调～"}</p>
        </Link>
      )}

      {/* 成员网格 */}
      <div className="guild-members-list">
        {loading ? (
          <ListLoading className="guild-members-loading" text="成员加载中..." />
        ) : gridMembers.length === 0 ? (
          <ListEmpty className="forum-empty" text="还没有成员" />
        ) : (
          <div className="guild-members-grid">
            {gridMembers.map((m) => (
              <Link key={m.id} className="guild-member-card" href={`/users/${m.id}`}>
                <div className="guild-member-avatar">
                  <UserAvatar src={m.avatar} alt={m.name} userId={m.id} vip={isVip(m.vip)} />
                </div>
                <div className="guild-member-name Username">{m.name}</div>
                <p className="guild-member-intro">{m.intro || "这个人很懒，什么都没留下~"}</p>
              </Link>
            ))}
          </div>
        )}
      </div>

      {hasMore && !loading && (
        <LoadMoreButton loading={loadingMore} onClick={loadMore} id="guild-members-load-more" />
      )}
    </div>
  );
}
