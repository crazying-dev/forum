// ===== 每日一言（彩蛋数据源：dlystc，客户端直连第三方 API）=====
// 失败 / 超时 / 非 200 一律返回 null，由调用方回退到原彩蛋逻辑。

export interface DailyQuote {
  text: string;
  from: string;
}

/** 启用每日一言时，彩蛋命中引言（而非原彩蛋）的概率 */
export const QUOTE_CHANCE = 0.5;

const QUOTE_API = `${process.env.NEXT_PUBLIC_API_BASE || ""}/ov2/api/site/daily-quote`;
const QUOTE_TIMEOUT_MS = 5000;

export async function fetchDailyQuote(): Promise<DailyQuote | null> {
  try {
    const res = await fetch(QUOTE_API, {
      cache: "no-store",
      signal: AbortSignal.timeout(QUOTE_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = (await res.json().catch(() => null)) as {
      success?: boolean;
      text?: unknown;
      source?: unknown;
    } | null;
    if (!data || data.success === false || typeof data.text !== "string" || !data.text.trim()) return null;
    // 长度上限：防止第三方返回超长文本拖垮提示条（超出截断并加省略号）
    const raw = data.text.trim();
    const text = raw.length > 300 ? `${raw.slice(0, 300)}…` : raw;
    const from = typeof data.source === "string" ? data.source.trim().slice(0, 100) : "";
    return { text, from };
  } catch {
    return null;
  }
}
