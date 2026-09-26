import { contrastText, themeColor } from "@/lib/constants";

/** 公共空间标签底色（深灰绿实底 + 白字，对比度 ≥ 4.5） */
const PUBLIC_SPACE_BG = "#3f5854";

/**
 * 空间标签（帖子/文章卡片、详情页用）：
 * - 会馆内容：该馆主题色实底胶囊 + 对比字 + 会馆名
 * - 公共内容：深灰绿实底胶囊「公共空间」
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
    const c = themeColor(color);
    return (
      <span className={className} style={{ background: c, color: contrastText(c) }} title={`会馆：${name}`}>
        <i className="fa fa-home"></i> {name}
      </span>
    );
  }
  return (
    <span
      className={`${className} space-badge-public`.trim()}
      title="公共空间"
      style={{ background: PUBLIC_SPACE_BG, color: "#fff" }}
    >
      <i className="fa fa-globe"></i> 公共空间
    </span>
  );
}
