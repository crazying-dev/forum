import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// OAuth 授权页（功能页：noindex；页面不渲染全局导航）
export const metadata: Metadata = pageMetadata({
  title: "OAuth 授权",
  description: "妖精论坛第三方应用授权页面。",
  path: "/oauth",
  index: false,
});

export default function OAuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
