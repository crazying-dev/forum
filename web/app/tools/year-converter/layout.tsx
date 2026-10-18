import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

// 无限年换算工具（公开）
export const metadata: Metadata = pageMetadata({
  title: "无限年换算",
  description: "妖精论坛无限年与公元年双向换算工具：无限元年 = 公元 1604 年，支持无限前、年/月/日校验与 2 月 29 日提示。",
  path: "/tools/year-converter",
});

export default function YearConverterLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
