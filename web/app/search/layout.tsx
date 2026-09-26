import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 搜索页（功能页：noindex；关键词联动标签页标题在页面内客户端更新）
export const metadata: Metadata = pageMetadata({
  title: "搜索",
  description: "在妖精论坛搜索帖子与用户。",
  path: "/search",
  index: false,
});

export default function SearchLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
