import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 邮箱验证页（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "邮箱验证",
  description: "验证妖精论坛账号的邮箱地址。",
  path: "/verify-email",
  index: false,
});

export default function VerifyEmailLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
