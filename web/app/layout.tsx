import type { Metadata, Viewport } from "next";
import "./globals.css";
import "font-awesome/css/font-awesome.min.css";
import "github-markdown-css/github-markdown.css";
import { StoreProvider } from "@/lib/store";
import { fetchApi, OG_IMAGE, SITE_DESCRIPTION, SITE_TITLE, siteUrl } from "@/lib/seo";
import { DEFAULT_SITE_CONFIG, isFestivalActive, type SiteConfig } from "@/lib/site-config";
import { CenterCardProvider } from "@/components/CenterCard";
import { ToastProvider } from "@/components/Toast";
import FestivalThemeSync from "@/components/FestivalThemeSync";
import Footer from "@/components/Footer";
import Header from "@/components/Header";

export const metadata: Metadata = {
  // 规范域名：SITE_URL → NEXT_PUBLIC_SITE_URL → https://yjlt.top
  // 预渲染页（首页/静态页/robots.txt）在构建期固化，建议构建前配置；动态详情页与 sitemap 运行期生效
  metadataBase: new URL(siteUrl()),
  title: {
    default: SITE_TITLE,
    template: "妖精论坛 - %s",
  },
  description: SITE_DESCRIPTION,
  keywords: ["妖精论坛", "罗小黑战记", "罗小黑", "同人社区", "二次元论坛", "会馆"],
  applicationName: "妖精论坛",
  // favicon 沿用 app/favicon.ico（Next.js 自动注入 <link rel="icon" type="image/x-icon" href="/favicon.ico">，与 legacy base.html 一致），不再重复声明 png 图标
  manifest: "/manifest.json",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "妖精论坛",
    locale: "zh_CN",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: "/",
    images: [OG_IMAGE],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [{ url: OG_IMAGE.url, alt: OG_IMAGE.alt }],
  },
};

export const viewport: Viewport = {
  // legacy base.html 中第二条 theme-color（#161b22）覆盖第一条，且 manifest theme_color 亦为 #161b22
  themeColor: "#161b22",
  width: "device-width",
  initialScale: 1,
};

// 防闪屏脚本：优先 localStorage，否则按时间
const themeScript = `
(function() {
  var theme = localStorage.getItem('forum-theme');
  if (theme === 'day') {
  } else if (theme === 'night') {
    document.documentElement.classList.add('night-mode');
  } else {
    var h = new Date().getHours();
    if (h < 6 || h >= 18) {
      document.documentElement.classList.add('night-mode');
    }
  }
})();
`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // 国庆主题：服务端按站点配置判定（60s 缓存），失败回退默认配置；
  // 客户端由 <FestivalThemeSync /> 在挂载 / 窗口聚焦时校正。
  const siteRes = await fetchApi<{ data: SiteConfig }>("/site/config", 60);
  const rawConfig = siteRes.ok ? siteRes.data?.data : null;
  const festivalActive = isFestivalActive(rawConfig ?? DEFAULT_SITE_CONFIG);

  return (
    // suppressHydrationWarning: 防闪屏脚本（themeScript）会在 hydration 前给 <html> 加 night-mode class，
    // 这是「hydration 前外部修改 DOM」的官方推荐场景，属性差异不报错且保留客户端已应用的主题
    <html lang="zh-CN" suppressHydrationWarning className={festivalActive ? "theme-national" : undefined}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body id="body">
        <StoreProvider>
          <ToastProvider>
            <CenterCardProvider>
              {/* 国庆主题客户端校正（无渲染输出） */}
              <FestivalThemeSync />
              {/* 全局导航栏：跨页面保持挂载，避免导航时品牌图等重载 */}
              <Header />
              <main className="app-main">{children}</main>
              <Footer />
            </CenterCardProvider>
          </ToastProvider>
        </StoreProvider>
      </body>
    </html>
  );
}
