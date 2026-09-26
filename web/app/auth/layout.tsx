import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 登录 / 注册（功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "登录 / 注册",
  description: "登录或注册妖精论坛账号，加入《罗小黑战记》同人社区。",
  path: "/auth",
  index: false,
});

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
