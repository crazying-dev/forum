import { themeColor, themeTint } from "@/lib/constants";
import { guildImageUrl } from "@/lib/media";

/** 会馆 Logo 图片地址：新 MD 媒体直出；旧 GridFS 走 /guild-img 兼容代理（需 guildUuid） */
export function guildLogoUrl(logoFileId?: string | null, guildUuid?: string | null, logoVersion?: number): string {
  return guildImageUrl(logoFileId, guildUuid, "logo", logoVersion);
}

/**
 * 会馆 Logo：has_logo 为真时走代理图片，否则主题色底色 + 名称首字占位。
 * 轮播 / 详情 / 列表统一使用本组件。
 */
export default function GuildLogo({
  logoFileId,
  guildUuid,
  logoVersion,
  name,
  hasLogo,
  color,
  size = 64,
  className = "guild-logo",
}: {
  logoFileId?: string | null;
  /** 会馆 uuid：旧 GridFS logo 经 /guild-img 兼容代理读取时必需 */
  guildUuid?: string | null;
  logoVersion?: number;
  name: string;
  hasLogo?: boolean;
  color?: string;
  size?: number;
  className?: string;
}) {
  const c = themeColor(color);
  const url = hasLogo ? guildLogoUrl(logoFileId, guildUuid, logoVersion) : "";

  if (url) {
    return (
      <div className={`${className} guild-logo-img`} style={{ width: size, height: size }}>
        <img src={url} alt={name} />
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
