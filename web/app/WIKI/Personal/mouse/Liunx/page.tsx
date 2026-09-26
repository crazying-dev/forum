import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Wiki · 鼠标主题（Linux 版）",
  description: "《罗小黑战记》鼠标主题 Linux 版说明与下载（未经授权禁止商用）。",
  path: "/WIKI/Personal/mouse/Liunx",
});

export default function LiunxPage() {
  return (
    <>
      <div className="wiki-page mouse-linux-page">
        <div className="wiki-header">
          <h2>罗小黑战记鼠标 - Linux版</h2>
          <p className="wiki-intro" style={{ color: "red" }}>未经授权禁止商用！！</p>
        </div>
        <div className="wiki-container">
          <div className="mouse-linux-download">
            <a href="/assets/mouse/lmxz_mouse_linux.zip" className="wiki-card" download>
              <div className="wiki-card-content">
                <i className="fa fa-download"></i>
                <h3>下载鼠标包</h3>
                <p>罗小黑战记鼠标 Linux版.zip</p>
              </div>
            </a>
          </div>
        </div>
      </div>
    </>
  );
}
