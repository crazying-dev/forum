// 分类标签与颜色（与 legacy AfterBody.js 保持 1:1）
export const CATEGORY_LABELS: Record<string, string> = {
  general: "综合", talk: "闲聊", question: "求助", share: "分享", creative: "创作",
};

export const CATEGORY_COLORS: Record<string, string> = {
  general: "#6A8C89",
  talk: "#f59e0b",
  question: "#ef4444",
  share: "#10b981",
  creative: "#8b5cf6",
};

/** 帖子分类选项（发帖页 / 论坛 Tab 共用，依 CATEGORY_LABELS 顺序） */
export const POST_CATEGORIES: { key: string; label: string }[] = [
  { key: "general", label: "综合" },
  { key: "talk", label: "闲聊" },
  { key: "question", label: "求助" },
  { key: "share", label: "分享" },
  { key: "creative", label: "创作" },
];

export function categoryLabel(category?: string): string {
  return CATEGORY_LABELS[category || ""] || category || "综合";
}

export function categoryColor(category?: string): string {
  return CATEGORY_COLORS[category || ""] || "#6A8C89";
}

// 会馆主题色：校验 hex（#RGB/#RRGGBB），非法时回退默认主色
const HEX_COLOR_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
export function themeColor(color?: string | null, fallback = "#6A8C89"): string {
  const c = (color || "").trim();
  return HEX_COLOR_RE.test(c) ? c : fallback;
}

// 主题色浅底（拼接透明度后缀，如 #6A8C89 + 22 ≈ 13%）；用于标签/卡片浅色背景
export function themeTint(color?: string | null, alpha = "22"): string {
  return themeColor(color) + alpha;
}

// ---- 颜色可读性（WCAG 对比度）----

// 解析 #RGB / #RRGGBB 为 [r,g,b]（0-255）；非法返回 null
function parseHex(hex?: string): [number, number, number] | null {
  const c = (hex || "").trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(c)) {
    return [parseInt(c[0] + c[0], 16), parseInt(c[1] + c[1], 16), parseInt(c[2] + c[2], 16)];
  }
  if (/^[0-9a-f]{6}$/i.test(c)) {
    return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
  }
  return null;
}

// sRGB 通道线性化（WCAG 2.x 公式）
function channelLum(v: number): number {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

// WCAG 相对亮度（0=纯黑，1=纯白）；非法色值按 0 处理
function luminanceOf(hex?: string): number {
  const rgb = parseHex(hex);
  if (!rgb) return 0;
  return 0.2126 * channelLum(rgb[0]) + 0.7152 * channelLum(rgb[1]) + 0.0722 * channelLum(rgb[2]);
}

// WCAG 对比度（1 ~ 21）
export function contrastRatio(a?: string, b?: string): number {
  const la = luminanceOf(a);
  const lb = luminanceOf(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

// 相对亮度阈值判断是否亮色（阈值 0.35：中间调偏亮即视为亮色，需配深色前景）
export function isLightHex(hex?: string, threshold = 0.35): boolean {
  return luminanceOf(hex) > threshold;
}

// 按 WCAG 对比度取更清晰的前景色：白 / 深灰
export function contrastText(hex?: string): "#fff" | "#1f2937" {
  if (!parseHex(hex)) return "#fff";
  return contrastRatio(hex, "#ffffff") >= contrastRatio(hex, "#1f2937") ? "#fff" : "#1f2937";
}

// 会馆 hero 前景色：亮色会馆用深字（#17323a），暗色会馆用白字
export const GUILD_FG_DARK = "#17323a";
export function guildForeground(hex?: string): string {
  return isLightHex(hex) ? GUILD_FG_DARK : "#ffffff";
}

// 主题色作为「卡片底上的文字/图标色」时的日间可读版本：亮色主题色压暗，
// 暗色主题色保持原色（夜间由 .theme-ink 规则向白色混合提亮）
export function themeInk(color?: string | null): string {
  const c = themeColor(color);
  const rgb = parseHex(c);
  if (!rgb || !isLightHex(c)) return c;
  const mix = (v: number) => Math.round(v * 0.45);
  return `rgb(${mix(rgb[0])}, ${mix(rgb[1])}, ${mix(rgb[2])})`;
}

// VIP 字段（"0" 表示非会员；空值不渲染）
export function isVip(vip?: string | null): boolean {
  return !!vip && vip !== "0";
}

// 相对时间（刚刚 / N分钟前 / N小时前 / N天前 / 日期）
export function timeAgo(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}天前`;
  return d.toLocaleDateString();
}

// 完整时间（帖子详情等）
export function formatTime(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString();
}

// 从出生日期（YYYYMMDD）自动计算岁数；兼容纯数字年龄；无则“保密”
export function ageDisplay(age?: string): string {
  const s = String(age || "").trim();
  if (!s) return "保密";
  if (/^\d{8}$/.test(s)) {
    const y = parseInt(s.substring(0, 4), 10);
    const m = parseInt(s.substring(4, 6), 10) - 1;
    const d = parseInt(s.substring(6, 8), 10);
    const dt = new Date(y, m, d);
    if (!isNaN(dt.getTime())) {
      const now = new Date();
      let a = now.getFullYear() - dt.getFullYear();
      const md = now.getMonth() - dt.getMonth();
      if (md < 0 || (md === 0 && now.getDate() < dt.getDate())) a--;
      return a + " 岁";
    }
  }
  const n = parseInt(s, 10);
  if (!isNaN(n)) return n + " 岁";
  return "保密";
}

// 时间（搜索/用户列表）
export function formatUserTime(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// HTML 转义（与 legacy escapeHtml 一致）
export function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// 按用户 ID 前缀生成身份徽章颜色（HG=蓝 / YJ=黄 / 全会馆=靛蓝）
// 返回 null 表示无徽章；返回值为颜色值。
export function prefixBadgeColor(userId?: string | null): string | null {
  if (!userId) return null;
  const prefix = userId.substring(0, 2).toUpperCase();
  const rest = userId.substring(2);
  if (prefix === "HG" && /^0+$/.test(rest)) return "#6366f1";
  if (prefix === "HG") return "#3b82f6";
  if (prefix === "YJ") return "#f59e0b";
  return null;
}
