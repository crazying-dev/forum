import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 消息中心（登录可见的功能页：noindex）
export const metadata: Metadata = pageMetadata({
  title: "消息中心",
  description: "查看点赞、评论、系统通知，并与论坛管理团队沟通。",
  path: "/messages",
  index: false,
});

export default function MessagesLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
