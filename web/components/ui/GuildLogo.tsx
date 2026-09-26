import { themeColor, themeTint } from "@/lib/constants";

/** 会馆 Logo 图片地址（经 next.config rewrites 的 /guild-img 代理到管理端） */
export function guildLogoUrl(id: number, logoVersion?: number): string {
  return `/guild-img/guilds/${id}/logo?v=${logoVersion || 0}`;
}

/**
 * 会馆 Logo：has_logo 为真时走代理图片，否则主题色底色 + 名称首字占位。
 * 轮播 / 详情 / 列表统一使用本组件。
 */
export default function GuildLogo({
  id,
  name,
  hasLogo,
  logoVersion,
  color,
  size = 64,
  className = "guild-logo",
}: {
  id: number;
  name: string;
  hasLogo?: boolean;
  logoVersion?: number;
  color?: string;
  size?: number;
  className?: string;
}) {
  const c = themeColor(color);

  if (hasLogo) {
    return (
      <div className={`${className} guild-logo-img`} style={{ width: size, height: size }}>
        <img src={guildLogoUrl(id, logoVersion)} alt={name} />
      </div>
    );
  }
  return (
    <div
      className={className}
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${c} 0%, ${themeTint(c, "66")} 100%)`,
        fontSize: Math.round(size * 0.44),
      }}
    >
      {(name || "馆").slice(0, 1)}
    </div>
  );
}
