import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 发帖页（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "发布新帖",
  description: "在妖精论坛发布新帖子，分享你的想法与故事。",
  path: "/post/create",
  index: false,
});

export default function PostCreateLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
