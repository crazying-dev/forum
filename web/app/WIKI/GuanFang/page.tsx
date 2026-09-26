import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Wiki · 官方",
  description: "《罗小黑战记》官方发布内容信息（因版权问题暂无法发布）。",
  path: "/WIKI/GuanFang",
});

export default function GuanFangPage() {
  return (
    <>
      <div className="wiki-page">
        <div className="wiki-header"><h2>罗小黑战记官方</h2><p style={{ color: "red" }}>因为版权问题无法发布</p></div>
        <div className="wiki-container"></div>
        <div className="wiki-footer"><p>更多内容持续更新中...</p></div>
      </div>
    </>
  );
}
