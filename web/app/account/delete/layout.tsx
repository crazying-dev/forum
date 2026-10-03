import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 账号注销页（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "账号注销",
  description: "注销妖精论坛账号。",
  path: "/account/delete",
  index: false,
});

export default function AccountDeleteLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
