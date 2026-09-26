import type { Metadata } from "next";
import WikiCard from "@/components/ui/WikiCard";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Wiki · 个人开发",
  description: "《罗小黑战记》个人创作与开发资源：鼠标主题、Live2D 模型等（未经授权禁止商用）。",
  path: "/WIKI/Personal",
});

export default function PersonalPage() {
  return (
    <>
      <div className="wiki-page">
        <div className="wiki-header"><h2>罗小黑战记个人开发</h2><h6 style={{ color: "red" }}>未经授权禁止商用！！</h6></div>
        <div className="wiki-container">
          <WikiCard href="/WIKI/Personal/mouse" img="/assets/img/mouse_banner.png" title="鼠标" desc="Liunx" />
          <WikiCard href="/WIKI/Personal/Live2D" img="/assets/img/AndSoOn.png" title="罗小黑Live2D模型(不可下载)" tip="查看详情 →" />
        </div>
        <div className="wiki-footer"><p>更多内容持续更新中...</p></div>
      </div>
    </>
  );
}
