import type { Metadata } from "next";
import WikiCard from "@/components/ui/WikiCard";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Wiki · 鼠标主题",
  description: "《罗小黑战记》鼠标主题下载与说明（未经授权禁止商用）。",
  path: "/WIKI/Personal/mouse",
});

export default function MouseIndexPage() {
  return (
    <>
      <div className="wiki-page">
        <div className="wiki-header"><h2>罗小黑战记鼠标</h2><h6 style={{ color: "red" }}>未经授权禁止商用！！</h6></div>
        <div className="wiki-container">
          <WikiCard href="/WIKI/Personal/mouse/Liunx" img="/assets/img/mouse_banner.png" title="Liunx版" />
          <WikiCard img="/assets/img/AndSoOn.png" title="等待更新" />
        </div>
        <div className="wiki-footer"><p>更多内容持续更新中...</p></div>
      </div>
    </>
  );
}
