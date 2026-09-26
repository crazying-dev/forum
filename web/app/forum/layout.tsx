import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 论坛广场（页面为客户端组件，标题/描述由本服务端布局提供）
export const metadata: Metadata = pageMetadata({
  title: "论坛广场",
  description: "妖精论坛广场：浏览全站最新帖子与会馆文章，支持按空间（公共 / 会馆）与分类筛选。",
  path: "/forum",
});

export default function ForumLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
