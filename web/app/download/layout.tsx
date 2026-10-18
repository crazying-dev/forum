import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 下载客户端（公开只读；数据源 GitHub Releases）
export const metadata: Metadata = pageMetadata({
  title: "下载客户端",
  description: "下载妖精论坛客户端：Windows / Android / Linux / macOS，查看最新版本、历史版本、SHA-256 与更新说明。",
  path: "/download",
});

export default function DownloadLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
