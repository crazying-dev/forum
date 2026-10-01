import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 论坛指南（公开只读）
export const metadata: Metadata = pageMetadata({
  title: "论坛指南",
  description: "妖精论坛使用指南与玩法说明。",
  path: "/guide",
});

export default function GuideLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
