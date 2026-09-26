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
export function themeColor(color?: string, fallback = "#6A8C89"): string {
  const c = (color || "").trim();
  return HEX_COLOR_RE.test(c) ? c : fallback;
}

// 主题色浅底（拼接透明度后缀，如 #6A8C89 + 22 ≈ 13%）；用于标签/卡片浅色背景
export function themeTint(color?: string, alpha = "22"): string {
  return themeColor(color) + alpha;
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

// 按 profile.prefix 字段生成徽章（搜索/资料卡）
export function prefixBadgeFor(prefix?: string): { color: string; text: string } | null {
  if (!prefix) return null;
  let color = "";
  if (prefix.startsWith("HG") && prefix !== "HG00000000000000000000") color = "#3b82f6";
  else if (prefix === "HG00000000000000000000") color = "#6366f1";
  else if (prefix === "YJ") color = "#f59e0b";
  if (!color) return null;
  return { color, text: prefix };
}
