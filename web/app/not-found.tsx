import type { Metadata } from "next";
import Link from "next/link";

// 404 页面：Next 会对 404 状态自动注入 <meta name="robots" content="noindex" />；
// 标题由本 metadata 提供（若运行期不支持将被根模板默认标题兼顾）。
export const metadata: Metadata = {
  title: "页面不存在",
};

export default function NotFound() {
  return (
    <div className="guild-empty" style={{ minHeight: "50vh", paddingTop: 100 }}>
      <i className="fa fa-compass"></i>
      <p className="guild-empty-title">页面不存在</p>
      <p className="guild-empty-desc">你访问的页面可能已被删除，或链接有误。</p>
      <Link className="guild-empty-link" href="/">
        返回首页 <i className="fa fa-arrow-right"></i>
      </Link>
    </div>
  );
}
