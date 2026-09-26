import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 会馆广场（页面为客户端组件，标题/描述由本服务端布局提供）。
// ⚠️ 本布局同时是 /huiguan/[slug] 的父段：标题须显式携带 title.template，
// 否则子段（会馆详情）的动态标题会丢失「妖精论坛 - 」前缀（Next.js 在
// 中间段遇到字符串标题时会重置模板暂存的行为）。
export const metadata: Metadata = {
  ...pageMetadata({
    title: "会馆广场",
    description: "妖精论坛会馆广场：走进会馆，遇见同好。浏览全部会馆、馆长与成员动态。",
    path: "/huiguan",
  }),
  title: { default: "会馆广场", template: "妖精论坛 - %s" },
};

export default function HuiGuanLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
