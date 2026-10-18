"use client";

// ===== 站点功能 API（更新日志 / 客户端下载）=====
// 端点见 docs/api/backend-contract.md 第 5 节：/changelogs、/downloads/*。
// 统一走 lib/api 的 request（同源 /ov2/api、credentials、success=false 抛 ApiException）。

import { request } from "@/lib/api";
import { apiUrl } from "@/lib/api-base";

// ---- 更新日志 ----

export interface ChangelogItem {
  id: number;
  version: string;
  title: string;
  content_html: string;
  /** RFC3339 */
  published_at: string;
}

export interface ChangelogListResult {
  success: boolean;
  items: ChangelogItem[];
  total: number;
  page: number;
  page_size: number;
}

export const changelogApi = {
  list: (page = 1, pageSize = 10) =>
    request<ChangelogListResult>(`/changelogs?page=${page}&page_size=${pageSize}`),
  detail: (id: number | string) =>
    request<{ success: boolean; item: ChangelogItem }>(`/changelogs/${encodeURIComponent(String(id))}`),
};

// ---- 客户端下载（数据源 GitHub Releases）----

export type ReleasePlatform = "windows" | "android" | "linux" | "macos";

export interface ReleaseItem {
  version: string;
  /** stable | beta */
  channel: string;
  /** YYYY-MM-DD */
  date: string;
  /** 字节数 */
  size: number;
  /** GitHub 直链 */
  url: string;
  filename: string;
  sha256: string;
  /** 旧客户端兼容的纯文本行列表 */
  notes: string[];
  /** Release 正文原始 Markdown（优先用于渲染） */
  notes_markdown: string;
  mandatory: boolean;
  platform: string;
}

export interface ReleaseListResult {
  success: boolean;
  items: ReleaseItem[];
  total: number;
  page: number;
  page_size: number;
}

/** GitHub Releases 页面（后端 GitHub 读取失败时的兜底直链） */
export const GITHUB_RELEASES_URL = "https://github.com/crazying-dev/forum/releases";

export const downloadApi = {
  list: (platform: string, page = 1, pageSize = 20) =>
    request<ReleaseListResult>(
      `/downloads/releases?page=${page}&page_size=${pageSize}&platform=${encodeURIComponent(platform)}`
    ),
  latest: (platform: string) =>
    request<{ success: boolean; item: ReleaseItem }>(`/downloads/latest?platform=${encodeURIComponent(platform)}`),
  /** 本站镜像下载地址（后端流式反代 GitHub 资产，支持 Range） */
  mirrorUrl: (platform: string, filename: string) =>
    apiUrl(`/downloads/mirror/${encodeURIComponent(platform)}/${encodeURIComponent(filename)}`),
};
