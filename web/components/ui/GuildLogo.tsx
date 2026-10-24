import { themeColor, themeTint } from "@/lib/constants";
import { mediaUrl } from "@/lib/media";

/** 会馆 Logo 图片地址（媒体直出：/ov2/api/media/<media_id>，不再经管理端代理） */
export function guildLogoUrl(logoFileId?: string | null): string {
  return mediaUrl(logoFileId);
}

/**
 * 会馆 Logo：has_logo 为真时走代理图片，否则主题色底色 + 名称首字占位。
 * 轮播 / 详情 / 列表统一使用本组件。
 */
export default function GuildLogo({
  logoFileId,
  name,
  hasLogo,
  color,
  size = 64,
  className = "guild-logo",
}: {
  logoFileId?: string | null;
  name: string;
  hasLogo?: boolean;
  color?: string;
  size?: number;
  className?: string;
}) {
  const c = themeColor(color);
  // 旧 GridFS 文件（ObjectID）已无法直出，mediaUrl 返回空串时回退占位图
  const url = hasLogo ? guildLogoUrl(logoFileId) : "";

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
