import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 外链跳转确认页（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "即将离开妖精论坛",
  description: "外部链接跳转确认页。",
  path: "/GoTo",
  index: false,
});

export default function GoToLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
