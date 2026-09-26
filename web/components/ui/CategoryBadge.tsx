import { categoryColor, categoryLabel, contrastText } from "@/lib/constants";

/** 分类徽章(彩色实底胶囊 + WCAG 对比字,避免浅底透背景) */
export default function CategoryBadge({
  category,
  className = "post-card-category",
}: {
  category?: string;
  className?: string;
}) {
  const catColor = categoryColor(category);
  return (
    <span className={className} style={{ background: catColor, color: contrastText(catColor) }}>
      {categoryLabel(category)}
    </span>
  );
}
