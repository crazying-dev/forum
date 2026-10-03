import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 重置密码链接页（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "重置密码",
  description: "通过邮箱重置链接设置新的登录密码。",
  path: "/reset-password",
  index: false,
});

export default function ResetPasswordLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
