"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PwaInstallButton from "@/components/PwaInstallButton";
import { useToast } from "@/components/Toast";
import { ApiException } from "@/lib/api";
import {
  downloadApi,
  GITHUB_RELEASES_URL,
  type ReleaseItem,
  type ReleasePlatform,
} from "@/lib/api/site-features";

const PAGE_SIZE = 20;

interface PlatformMeta {
  key: ReleasePlatform;
  name: string;
  icon: string;
  requirement: string;
}

const PLATFORMS: PlatformMeta[] = [
  { key: "windows", name: "Windows", icon: "fa-windows", requirement: "Windows 10 / 11" },
  { key: "android", name: "Android", icon: "fa-android", requirement: "Android 8.0 及以上" },
  { key: "linux", name: "Linux", icon: "fa-linux", requirement: "AppImage / deb / rpm" },
  { key: "macos", name: "macOS", icon: "fa-apple", requirement: "macOS 11 及以上" },
];

/** v 前缀归一（避免后端 version 已带 v 时出现 vv） */
function versionLabel(version: string): string {
  const v = (version || "").trim();
  if (!v) return "—";
  return /^v/i.test(v) ? v : `v${v}`;
}

/** 字节数 → 易读大小 */
function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "未知";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`;
}

/** YYYY-MM-DD（无效值原样展示） */
function formatDate(value: string): string {
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function channelLabel(channel: string): string {
  return channel === "beta" ? "测试版" : "稳定版";
}

function platformName(key: string): string {
  return PLATFORMS.find((p) => p.key === key)?.name || key;
}

/** 下载客户端：平台 Tab + 最新版大卡 + 历史版本折叠（20/页）+ PWA 安装 */
export default function DownloadPage() {
  const { toast } = useToast();
  const [platform, setPlatform] = useState<ReleasePlatform>("windows");

  const [latest, setLatest] = useState<ReleaseItem | null>(null);
  const [latestLoading, setLatestLoading] = useState(true);
  const [latestError, setLatestError] = useState("");

  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<ReleaseItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const latestSeqRef = useRef(0);
  const historySeqRef = useRef(0);

  const loadLatest = useCallback(async (target: ReleasePlatform) => {
    const seq = ++latestSeqRef.current;
    setLatestLoading(true);
    setLatestError("");
    setLatest(null);
    try {
      const data = await downloadApi.latest(target);
      if (seq !== latestSeqRef.current) return;
      setLatest(data.item || null);
    } catch (e) {
      if (seq !== latestSeqRef.current) return;
      setLatestError(e instanceof ApiException ? e.message : "获取发布信息失败");
    } finally {
      if (seq === latestSeqRef.current) setLatestLoading(false);
    }
  }, []);

  const loadHistory = useCallback(
    async (targetPage: number) => {
      const seq = ++historySeqRef.current;
      setHistoryLoading(true);
      setHistoryError("");
      try {
        const data = await downloadApi.list(platform, targetPage, PAGE_SIZE);
        if (seq !== historySeqRef.current) return;
        setHistoryItems(data.items || []);
        setHistoryTotal(data.total || 0);
        setHistoryPage(data.page || targetPage);
      } catch (e) {
        if (seq !== historySeqRef.current) return;
        setHistoryItems([]);
        setHistoryTotal(0);
        setHistoryError(e instanceof ApiException ? e.message : "历史版本加载失败");
      } finally {
        if (seq === historySeqRef.current) setHistoryLoading(false);
      }
    },
    [platform]
  );

  useEffect(() => {
    // 延后一个 tick 发起请求，避免在 effect 内同步更新加载态
    const t = window.setTimeout(() => void loadLatest(platform), 0);
    return () => window.clearTimeout(t);
  }, [platform, loadLatest]);

  useEffect(() => {
    if (!historyOpen) return;
    const t = window.setTimeout(() => void loadHistory(1), 0);
    return () => window.clearTimeout(t);
  }, [historyOpen, platform, loadHistory]);

  // 平台 Tab 与 URL hash 同步（与 legacy /Download#android 行为一致）
  useEffect(() => {
    const applyHash = () => {
      const key = (window.location.hash || "").replace("#", "").toLowerCase();
      if (PLATFORMS.some((p) => p.key === key)) setPlatform(key as ReleasePlatform);
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  const selectPlatform = (key: ReleasePlatform) => {
    if (key === platform) return;
    setPlatform(key);
    setHistoryOpen(false);
    try {
      history.replaceState(null, "", `#${key}`);
    } catch {
      /* 忽略 */
    }
  };

  const copyText = async (text: string, label: string) => {
    if (!text) {
      toast(`没有可复制的${label}`, "warning");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      toast(`${label}已复制`, "success");
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "readonly");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        toast(ok ? `${label}已复制` : "复制失败，请手动选择复制", ok ? "success" : "error");
      } catch {
        toast("复制失败，请手动选择复制", "error");
      }
    }
  };

  const currentPlatform = PLATFORMS.find((p) => p.key === platform) || PLATFORMS[0];
  const historyTotalPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE));
  const latestDownloadUrl = latest
    ? latest.filename
      ? downloadApi.mirrorUrl(platform, latest.filename)
      : latest.url
    : "";

  return (
    <div className="download-page">
      <header className="download-hero">
        <h1 className="download-heading">
          <i className="fa fa-download" aria-hidden="true"></i> 下载客户端
        </h1>
        <p className="download-subtitle">
          妖精论坛客户端 —— 论坛 / 世界频道 / WIKI / 彩蛋一站式入口。支持 Windows、Android、Linux 与 macOS。
        </p>
      </header>

      <div className="download-platform-tabs" role="tablist" aria-label="选择平台">
        {PLATFORMS.map((p) => (
          <button
            key={p.key}
            type="button"
            role="tab"
            aria-selected={platform === p.key}
            className={`download-tab${platform === p.key ? " active" : ""}`}
            onClick={() => selectPlatform(p.key)}
          >
            <i className={`fa ${p.icon}`} aria-hidden="true"></i>
            <span>{p.name}</span>
          </button>
        ))}
      </div>

      <p className="download-requirement">
        <i className="fa fa-desktop" aria-hidden="true"></i> {currentPlatform.name} 运行环境：{currentPlatform.requirement}
      </p>

      {latestLoading ? (
        <section className="download-latest-card download-latest-loading" role="status">
          <i className="fa fa-spinner fa-spin" aria-hidden="true"></i> 正在获取最新版本...
        </section>
      ) : latestError ? (
        <section className="download-latest-card download-error" role="alert">
          <h2 className="download-error-title">
            <i className="fa fa-exclamation-triangle" aria-hidden="true"></i> 获取发布信息失败
          </h2>
          <p className="download-error-message">{latestError}</p>
          <p className="download-error-hint">如 GitHub Releases 暂时不可用，你也可以直接前往 GitHub 查看或下载：</p>
          <div className="download-actions">
            <a
              className="download-btn download-btn-primary"
              href={GITHUB_RELEASES_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              <i className="fa fa-github" aria-hidden="true"></i> 前往 GitHub Releases
            </a>
            <button type="button" className="download-btn download-btn-outline" onClick={() => void loadLatest(platform)}>
              <i className="fa fa-refresh" aria-hidden="true"></i> 重试
            </button>
          </div>
        </section>
      ) : latest ? (
        <section className="download-latest-card" aria-labelledby="download-latest-title">
          <div className="download-latest-head">
            <div className="download-latest-title-wrap">
              <span className="download-kicker">最新版本</span>
              <h2 className="download-version" id="download-latest-title">{versionLabel(latest.version)}</h2>
              <div className="download-badges">
                <span className={`download-badge${latest.channel === "beta" ? " download-badge-beta" : ""}`}>
                  {channelLabel(latest.channel)}
                </span>
                <span className="download-badge download-badge-platform">{platformName(latest.platform || platform)}</span>
                {latest.mandatory && (
                  <span className="download-badge download-badge-warn">
                    <i className="fa fa-exclamation-circle" aria-hidden="true"></i> 强制更新
                  </span>
                )}
              </div>
            </div>
            <PwaInstallButton className="download-btn download-btn-soft download-pwa-btn" />
          </div>

          <dl className="download-meta">
            <div className="download-meta-item">
              <dt><i className="fa fa-calendar" aria-hidden="true"></i> 发布日期</dt>
              <dd>{formatDate(latest.date)}</dd>
            </div>
            <div className="download-meta-item">
              <dt><i className="fa fa-hdd-o" aria-hidden="true"></i> 文件大小</dt>
              <dd>{formatSize(latest.size)}</dd>
            </div>
            <div className="download-meta-item download-meta-file">
              <dt><i className="fa fa-file-archive-o" aria-hidden="true"></i> 文件名</dt>
              <dd>{latest.filename || "—"}</dd>
            </div>
          </dl>

          <div className="download-sha-row">
            <span className="download-sha-label">SHA-256</span>
            <code className="download-sha-value">{latest.sha256 || "未提供"}</code>
            {latest.sha256 && (
              <button
                type="button"
                className="download-copy-btn"
                onClick={() => void copyText(latest.sha256, "SHA-256")}
                aria-label="复制 SHA-256"
              >
                <i className="fa fa-copy" aria-hidden="true"></i> 复制
              </button>
            )}
          </div>

          <div className="download-notes-block">
            <h3 className="download-notes-title">更新说明</h3>
            {latest.notes && latest.notes.length > 0 ? (
              <ul className="download-notes">
                {latest.notes.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            ) : (
              <p className="download-notes-empty">暂无更新说明</p>
            )}
          </div>

          <div className="download-actions">
            <a className="download-btn download-btn-primary" href={latestDownloadUrl || latest.url}>
              <i className="fa fa-download" aria-hidden="true"></i> 下载 {versionLabel(latest.version)}
            </a>
            {latest.url && (
              <a
                className="download-btn download-btn-outline"
                href={latest.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <i className="fa fa-github" aria-hidden="true"></i> GitHub 直链
              </a>
            )}
            {latest.filename && (
              <button
                type="button"
                className="download-btn download-btn-outline"
                onClick={() => void copyText(downloadApi.mirrorUrl(platform, latest.filename), "镜像链接")}
              >
                <i className="fa fa-link" aria-hidden="true"></i> 复制镜像链接
              </button>
            )}
          </div>
          <p className="download-hint">下载由本站服务器中转（GitHub 反代，支持断点续传）；非本站来源请勿轻信。</p>
        </section>
      ) : (
        <section className="download-latest-card download-empty">
          <i className="fa fa-inbox" aria-hidden="true"></i> 该平台暂无可用安装包，请稍后再来看看。
        </section>
      )}

      <section className="download-history">
        <button
          type="button"
          className="download-history-toggle"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen((open) => !open)}
        >
          <span className="download-history-toggle-label">
            <i className="fa fa-archive" aria-hidden="true"></i> 历史版本
            <span className="download-history-hint">每页 20 条</span>
          </span>
          <i className={`fa ${historyOpen ? "fa-chevron-up" : "fa-chevron-down"}`} aria-hidden="true"></i>
        </button>

        {historyOpen && (
          <div className="download-history-body">
            <div className="download-history-warning">
              <i className="fa fa-exclamation-triangle" aria-hidden="true"></i>
              历史版本可能存在已知问题或安全风险，请优先下载最新版。
            </div>

            {historyLoading ? (
              <div className="download-history-status" role="status">
                <i className="fa fa-spinner fa-spin" aria-hidden="true"></i> 加载历史版本...
              </div>
            ) : historyError ? (
              <div className="download-history-status download-error" role="alert">
                <p>{historyError}</p>
                <div className="download-actions">
                  <a
                    className="download-btn download-btn-outline"
                    href={GITHUB_RELEASES_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <i className="fa fa-github" aria-hidden="true"></i> GitHub Releases
                  </a>
                  <button type="button" className="download-btn download-btn-outline" onClick={() => void loadHistory(historyPage)}>
                    <i className="fa fa-refresh" aria-hidden="true"></i> 重试
                  </button>
                </div>
              </div>
            ) : historyItems.length === 0 ? (
              <div className="download-history-status">该平台暂无历史版本</div>
            ) : (
              <div className="download-release-list">
                {historyItems.map((item, idx) => {
                  const mirror = item.filename ? downloadApi.mirrorUrl(platform, item.filename) : item.url;
                  return (
                    <article className="download-release" key={`${item.version}-${item.filename}-${idx}`}>
                      <div className="download-release-head">
                        <span className="download-release-version">{versionLabel(item.version)}</span>
                        <span className="download-badge download-badge-small">{channelLabel(item.channel)}</span>
                        {item.mandatory && (
                          <span className="download-badge download-badge-warn download-badge-small">强制更新</span>
                        )}
                        <span className="download-release-date">{formatDate(item.date)}</span>
                        <span className="download-release-size">{formatSize(item.size)}</span>
                      </div>
                      {item.notes && item.notes.length > 0 && (
                        <ul className="download-notes download-notes-small">
                          {item.notes.map((note, noteIdx) => (
                            <li key={noteIdx}>{note}</li>
                          ))}
                        </ul>
                      )}
                      <div className="download-sha-row download-sha-compact">
                        <span className="download-sha-label">SHA-256</span>
                        <code className="download-sha-value">{item.sha256 || "未提供"}</code>
                      </div>
                      <div className="download-release-actions">
                        <a className="download-link" href={mirror || item.url}>
                          <i className="fa fa-download" aria-hidden="true"></i> 镜像下载
                        </a>
                        {item.url && (
                          <a className="download-link" href={item.url} target="_blank" rel="noopener noreferrer">
                            <i className="fa fa-github" aria-hidden="true"></i> GitHub
                          </a>
                        )}
                        {item.filename && (
                          <button
                            type="button"
                            className="download-link download-link-btn"
                            onClick={() => void copyText(downloadApi.mirrorUrl(platform, item.filename), "镜像链接")}
                          >
                            <i className="fa fa-link" aria-hidden="true"></i> 复制链接
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}

            {!historyLoading && !historyError && historyTotalPages > 1 && (
              <nav className="download-pagination" aria-label="历史版本分页">
                <button
                  type="button"
                  className="download-page-btn"
                  disabled={historyPage <= 1}
                  onClick={() => void loadHistory(historyPage - 1)}
                >
                  <i className="fa fa-chevron-left" aria-hidden="true"></i> 上一页
                </button>
                <span className="download-page-info">第 {historyPage} / {historyTotalPages} 页</span>
                <button
                  type="button"
                  className="download-page-btn"
                  disabled={historyPage >= historyTotalPages}
                  onClick={() => void loadHistory(historyPage + 1)}
                >
                  下一页 <i className="fa fa-chevron-right" aria-hidden="true"></i>
                </button>
              </nav>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
