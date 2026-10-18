import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 更新日志（公开只读）
export const metadata: Metadata = pageMetadata({
  title: "更新日志",
  description: "妖精论坛更新日志：版本功能上新、体验优化与问题修复记录。",
  path: "/changelog",
});

export default function ChangelogLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
