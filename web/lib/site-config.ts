// ===== 站点配置（站点级开关：国庆主题 / 每日一言 / 首页公告）=====
// 纯工具模块（不加 "use client"）：
// - 服务端（layout.tsx）只用纯函数 todayMmDd / isFestivalActive 与 DEFAULT_SITE_CONFIG；
// - 浏览器端通过同源相对路径 /ov2/api/site/config 拉取，60s 模块级缓存 + 进行中请求去重；
// - 任何失败返回 null（短暂缓存），消费方按各自兜底策略处理（主题保持现状 / 彩蛋视为未启用）。

export interface SiteAnnouncement {
  enabled: boolean;
  /** 纯文本公告（非富文本，消费方按文本节点渲染） */
  text: string;
  /** 公告版本号：内容更新时由后端递增，用于 localStorage 关闭态去重 */
  version: number;
  updated_at: string;
}

export interface SiteConfig {
  theme: { mode: "auto" | "on" | "off"; start: string; end: string };
  daily_quote: { enabled: boolean; provider: string };
  announcement: SiteAnnouncement;
}

/** 服务端拉取失败 / 客户端不可达时的默认配置（国庆 10-01～10-07 自动开启；每日一言 / 公告关闭） */
export const DEFAULT_SITE_CONFIG: SiteConfig = {
  theme: { mode: "auto", start: "10-01", end: "10-07" },
  daily_quote: { enabled: false, provider: "dlystc" },
  announcement: { enabled: false, text: "", version: 0, updated_at: "" },
};

/** 上海时区「今天」的 MM-DD（如 10-03）；用 Intl 格式化避免受访问端本地时区影响 */
export function todayMmDd(): string {
  const ymd = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return ymd.slice(5, 10);
}

/** 今日是否处于节日主题期：on 强制开启 / off 关闭 / auto 按 MM-DD 区间（字符串比较） */
export function isFestivalActive(cfg: SiteConfig | null | undefined): boolean {
  const theme = cfg?.theme;
  if (!theme) return false;
  if (theme.mode === "on") return true;
  if (theme.mode === "off") return false;
  const today = todayMmDd();
  return (
    typeof theme.start === "string" &&
    typeof theme.end === "string" &&
    theme.start <= today &&
    today <= theme.end
  );
}

const CACHE_TTL_MS = 60_000; // 成功结果缓存 60s
const FAIL_CACHE_TTL_MS = 10_000; // 失败（null）短暂缓存，避免请求风暴

let cachedAt = 0;
let cachedData: SiteConfig | null = null;
let inflight: Promise<SiteConfig | null> | null = null;

/** 字段级防御解析：形状非法返回 null，缺失字段回落默认值，避免消费方拿到半成品崩溃 */
function parseSiteConfig(raw: unknown): SiteConfig | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as { theme?: unknown; daily_quote?: unknown; announcement?: unknown };
  if (!obj.theme || typeof obj.theme !== "object" || !obj.daily_quote || typeof obj.daily_quote !== "object") {
    return null;
  }
  const theme = obj.theme as Partial<SiteConfig["theme"]>;
  const quote = obj.daily_quote as Partial<SiteConfig["daily_quote"]>;
  // 公告字段缺失/形状非法时回落默认值（旧后端无 announcement 也能正常解析）
  // version 兼容后端数字 / 管理端可能写入的字符串，故按 unknown 校验（不直接用 Partial<SiteAnnouncement> 收窄）
  const announcement = (obj.announcement && typeof obj.announcement === "object" ? obj.announcement : {}) as {
    enabled?: unknown;
    text?: unknown;
    version?: unknown;
    updated_at?: unknown;
  };
  const version =
    typeof announcement.version === "number" && Number.isFinite(announcement.version)
      ? Math.trunc(announcement.version)
      : typeof announcement.version === "string" && /^\d+$/.test(announcement.version.trim())
        ? Number.parseInt(announcement.version.trim(), 10)
        : 0;
  return {
    theme: {
      mode: theme.mode === "on" || theme.mode === "off" ? theme.mode : "auto",
      start: typeof theme.start === "string" ? theme.start : DEFAULT_SITE_CONFIG.theme.start,
      end: typeof theme.end === "string" ? theme.end : DEFAULT_SITE_CONFIG.theme.end,
    },
    daily_quote: {
      enabled: quote.enabled === true,
      provider: typeof quote.provider === "string" ? quote.provider : DEFAULT_SITE_CONFIG.daily_quote.provider,
    },
    announcement: {
      enabled: announcement.enabled === true,
      text: typeof announcement.text === "string" ? announcement.text : "",
      version,
      updated_at: typeof announcement.updated_at === "string" ? announcement.updated_at : "",
    },
  };
}

async function loadSiteConfig(): Promise<SiteConfig | null> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE || ""}/ov2/api/site/config`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const body = (await res.json().catch(() => null)) as { success?: boolean; data?: unknown } | null;
    if (!body || body.success === false) return null;
    return parseSiteConfig(body.data);
  } catch {
    return null;
  }
}

/** 获取站点配置（模块级缓存 60s、失败短暂缓存、进行中请求去重）；不可用时返回 null */
export function getSiteConfig(): Promise<SiteConfig | null> {
  if (cachedAt && Date.now() - cachedAt < (cachedData ? CACHE_TTL_MS : FAIL_CACHE_TTL_MS)) {
    return Promise.resolve(cachedData);
  }
  if (inflight) return inflight;
  const p = loadSiteConfig()
    .then((data) => {
      cachedAt = Date.now();
      cachedData = data;
      return data;
    })
    .finally(() => {
      inflight = null;
    });
  inflight = p;
  return p;
}
