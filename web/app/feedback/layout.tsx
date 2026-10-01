import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 反馈中心（功能页：公开只读、noindex）
export const metadata: Metadata = pageMetadata({
  title: "反馈中心",
  description: "查看妖精论坛反馈的处理进度与结果。",
  path: "/feedback",
  index: false,
});

export default function FeedbackLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
