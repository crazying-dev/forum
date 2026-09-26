import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// Live2D 模型页（页面为客户端组件，标题/描述由本服务端布局提供）
export const metadata: Metadata = pageMetadata({
  title: "Wiki · Live2D 模型",
  description: "《罗小黑战记》Live2D 模型展示与说明（不可下载，未经授权禁止商用）。",
  path: "/WIKI/Personal/Live2D",
});

export default function Live2DLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
