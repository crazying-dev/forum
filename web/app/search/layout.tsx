import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 搜索页（功能页：noindex；关键词联动标签页标题在页面内客户端更新）
export const metadata: Metadata = pageMetadata({
  title: "搜索",
  description: "搜索帖子、用户与文章",
  path: "/search",
  index: false,
});

export default function SearchLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
