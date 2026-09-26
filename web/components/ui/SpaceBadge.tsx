import { themeColor, themeTint } from "@/lib/constants";

/**
 * 空间标签（帖子/文章卡片用）：
 * - 会馆内容：该馆主题色浅底胶囊 + 会馆名
 * - 公共内容：灰色胶囊「公共空间」
 */
export default function SpaceBadge({
  name,
  color,
  className = "space-badge",
}: {
  name?: string | null;
  color?: string | null;
  className?: string;
}) {
  if (name) {
    return (
      <span className={className} style={{ background: themeTint(color || undefined), color: themeColor(color || undefined) }} title={`会馆：${name}`}>
        <i className="fa fa-home"></i> {name}
      </span>
    );
  }
  return (
    <span className={`${className} space-badge-public`.trim()} title="公共空间">
      <i className="fa fa-globe"></i> 公共空间
    </span>
  );
}
