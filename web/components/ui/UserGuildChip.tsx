"use client";

import { contrastText, themeColor } from "@/lib/constants";

/**
 * 用户身份小 chip（帖子/评论/卡片作者旁）：
 * - 会馆名：会馆主题色实底 + 对比字
 * - 「馆长」：低饱和墨绿实底（#5b736e）+ 白字，crown 图标随字色（见 app/styles/ui-fixes.css .user-leader-chip）
 * 字段缺失（user_guild_name 为空）时不渲染。
 */
export function UserGuildChip({
  name,
  color,
  isLeader = false,
}: {
  name?: string | null;
  color?: string | null;
  isLeader?: boolean;
}) {
  if (!name) return null;
  const c = themeColor(color);
  return (
    <>
      <span className="user-guild-chip" style={{ background: c, color: contrastText(c) }} title={`会馆：${name}`}>
        <i className="fa fa-home"></i>
        {name}
      </span>
      {isLeader && (
        <span className="user-guild-chip user-leader-chip" title="会馆馆长">
          <i className="fa fa-crown"></i>
          馆长
        </span>
      )}
    </>
  );
}