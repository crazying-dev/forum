"use client";

import { type FormEvent, useEffect, useState } from "react";

// ===== 无限历 ⇄ 公元历换算（与 legacy AfterBody.js 的年制口径一致）=====
// 无限元年 = 公元 1604 年；无限 N 年 = 公元 (1603 + N) 年；
// 公元 1603 年及以前 = 无限前 (1604 - 公元年) 年；两套纪年都不存在 0 年。
const INFINITE_EPOCH = 1604;

type InfiniteEra = "after" | "before";
type GregorianEra = "ce" | "bce";
type ResultType = "success" | "warning" | "error";

interface ConversionResult {
  type: ResultType;
  message: string;
}

interface InfiniteForm {
  era: InfiniteEra;
  year: string;
  month: string;
  day: string;
}

interface GregorianForm {
  era: GregorianEra;
  year: string;
  month: string;
  day: string;
}

interface Today {
  year: number;
  month: number;
  day: number;
}

/** 公历闰年（天文纪年；公元前 1 年 = 天文年 0，按 400 年周期仍为闰年） */
function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

/** 指定公历年月天数 */
function daysInMonth(year: number, month: number): number {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  if (month === 4 || month === 6 || month === 9 || month === 11) return 30;
  return 31;
}

/** 解析非负整数（仅 ASCII 数字；非法 / 溢出返回 null） */
function parseInteger(raw: string): number | null {
  const s = raw.trim();
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  return Number.isSafeInteger(n) ? n : null;
}

/** 公元年展示：公元纪年没有 0 年，天文年 0 = 公元前 1 年 */
function gregorianLabel(year: number): string {
  return year >= 1 ? `公元 ${year} 年` : `公元前 ${1 - year} 年`;
}

/** 无限年年份名：无限元年 / 无限 N 年 / 无限前 N 年 */
function infiniteLabel(year: number, before: boolean): string {
  if (before) return `无限前 ${year} 年`;
  return year === 1 ? "无限元年" : `无限 ${year} 年`;
}

/** 天文公历年 → 无限历（无限元年 = 1604；1604 之前为无限前） */
function toInfinite(year: number): { year: number; before: boolean } {
  return year >= INFINITE_EPOCH
    ? { year: year - INFINITE_EPOCH + 1, before: false }
    : { year: INFINITE_EPOCH - year, before: true };
}

/** 无限历 → 天文公历年（before 的 1 年 = 1603，即公元前 1 年 = 天文年 0） */
function toGregorian(year: number, before: boolean): number {
  return before ? INFINITE_EPOCH - year : year + INFINITE_EPOCH - 1;
}

/** 上海时区「今天」（与论坛签到 / 时间展示口径一致） */
function shanghaiToday(): Today {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0);
  return { year: pick("year"), month: pick("month"), day: pick("day") };
}

/** 校验月/日输入 */
function parseMonthDay(monthRaw: string, dayRaw: string): { month: number; day: number } | { error: string } {
  const month = parseInteger(monthRaw);
  if (month === null || month < 1 || month > 12) return { error: "请输入 1-12 的月份" };
  const day = parseInteger(dayRaw);
  if (day === null || day < 1 || day > 31) return { error: "请输入 1-31 的日期" };
  return { month, day };
}

/** 目标日期合法性：2 月 29 日落在非闰年时给出明确提示 */
function checkDate(year: number, month: number, day: number): { error?: string; feb29?: boolean } {
  const max = daysInMonth(year, month);
  if (day <= max) return {};
  if (month === 2 && day === 29 && !isLeapYear(year)) {
    return { error: `目标${gregorianLabel(year)}不是闰年，2 月 29 日不存在`, feb29: true };
  }
  return { error: `${gregorianLabel(year)}的 ${month} 月只有 ${max} 天` };
}

/** 无限历 → 公元历 */
function convertInfiniteToGregorian(form: InfiniteForm): ConversionResult {
  const year = parseInteger(form.year);
  if (year === null) return { type: "error", message: "请输入有效的无限年年份" };
  if (year === 0) return { type: "error", message: "无限历没有 0 年（元年即公元 1604 年）" };
  const md = parseMonthDay(form.month, form.day);
  if ("error" in md) return { type: "error", message: md.error };
  const gregorianYear = toGregorian(year, form.era === "before");
  const checked = checkDate(gregorianYear, md.month, md.day);
  if (checked.error) {
    return { type: checked.feb29 ? "warning" : "error", message: checked.error };
  }
  return {
    type: "success",
    message: `${infiniteLabel(year, form.era === "before")} ${md.month} 月 ${md.day} 日 = ${gregorianLabel(gregorianYear)} ${md.month} 月 ${md.day} 日`,
  };
}

/** 公元历 → 无限历 */
function convertGregorianToInfinite(form: GregorianForm): ConversionResult {
  const year = parseInteger(form.year);
  if (year === null) return { type: "error", message: "请输入有效的公元年份" };
  if (year === 0) return { type: "error", message: "公元纪年没有 0 年（公元前 1 年之后即公元 1 年）" };
  const md = parseMonthDay(form.month, form.day);
  if ("error" in md) return { type: "error", message: md.error };
  // 公元前 1 年 = 天文年 0；公元前 N 年 = 天文年 (1 - N)
  const astronomicalYear = form.era === "bce" ? 1 - year : year;
  const checked = checkDate(astronomicalYear, md.month, md.day);
  if (checked.error) {
    return { type: checked.feb29 ? "warning" : "error", message: checked.error };
  }
  const infinite = toInfinite(astronomicalYear);
  return {
    type: "success",
    message: `${gregorianLabel(astronomicalYear)} ${md.month} 月 ${md.day} 日 = ${infiniteLabel(infinite.year, infinite.before)} ${md.month} 月 ${md.day} 日`,
  };
}

function ResultPanel({ result }: { result: ConversionResult | null }) {
  if (!result) {
    return (
      <div className="yc-result yc-result-idle">
        <i className="fa fa-info-circle" aria-hidden="true"></i>
        <p>填写年、月、日后点击「换算」查看结果</p>
      </div>
    );
  }
  const icon =
    result.type === "success" ? "fa-check-circle" : result.type === "warning" ? "fa-exclamation-triangle" : "fa-times-circle";
  return (
    <div className={`yc-result yc-result-${result.type}`} role={result.type === "error" ? "alert" : "status"}>
      <i className={`fa ${icon}`} aria-hidden="true"></i>
      <p>{result.message}</p>
    </div>
  );
}

/** 无限年换算：无限历 ⇄ 公元历 双向（年/月/日），含无限前 / 0 年 / 闰日校验 */
export default function YearConverterPage() {
  const [today, setToday] = useState<Today | null>(null);
  const [infiniteForm, setInfiniteForm] = useState<InfiniteForm>({ era: "after", year: "", month: "", day: "" });
  const [gregorianForm, setGregorianForm] = useState<GregorianForm>({ era: "ce", year: "", month: "", day: "" });
  const [infiniteResult, setInfiniteResult] = useState<ConversionResult | null>(null);
  const [gregorianResult, setGregorianResult] = useState<ConversionResult | null>(null);

  useEffect(() => {
    // 时钟属于外部系统：挂载后一个 tick 再读，避免 SSR/客户端首帧时区差异与同步 setState
    const t = window.setTimeout(() => setToday(shanghaiToday()), 0);
    return () => window.clearTimeout(t);
  }, []);

  const updateInfinite = (patch: Partial<InfiniteForm>) => {
    setInfiniteForm((prev) => ({ ...prev, ...patch }));
  };
  const updateGregorian = (patch: Partial<GregorianForm>) => {
    setGregorianForm((prev) => ({ ...prev, ...patch }));
  };

  const submitInfinite = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setInfiniteResult(convertInfiniteToGregorian(infiniteForm));
  };
  const submitGregorian = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setGregorianResult(convertGregorianToInfinite(gregorianForm));
  };

  const todayInfinite = today ? toInfinite(today.year) : null;

  return (
    <div className="year-converter-page">
      <header className="yc-header">
        <h1 className="yc-heading">
          <i className="fa fa-calendar" aria-hidden="true"></i> 无限年换算
        </h1>
        <p className="yc-subtitle">
          在「无限历」与「公元历」之间双向换算年、月、日。基准：无限元年 = 公元 1604 年。
        </p>
        {today && todayInfinite && (
          <div className="yc-today">
            <i className="fa fa-clock-o" aria-hidden="true"></i>
            <span>
              今天是 {gregorianLabel(today.year)} {today.month} 月 {today.day} 日
            </span>
            <span className="yc-today-sep" aria-hidden="true">·</span>
            <span>
              {infiniteLabel(todayInfinite.year, todayInfinite.before)} {today.month} 月 {today.day} 日
            </span>
          </div>
        )}
      </header>

      <div className="yc-grid">
        <section className="yc-card" aria-labelledby="yc-infinite-title">
          <h2 className="yc-card-title" id="yc-infinite-title">
            <i className="fa fa-long-arrow-right" aria-hidden="true"></i> 无限历 → 公元历
          </h2>
          <p className="yc-card-desc">公元 1604 年之前为「无限前」，请切换纪年并填写正数年份。</p>
          <form className="yc-form" onSubmit={submitInfinite}>
            <div className="yc-field-row">
              <label className="yc-field">
                <span>纪年</span>
                <select value={infiniteForm.era} onChange={(e) => updateInfinite({ era: e.target.value as InfiniteEra })}>
                  <option value="after">无限</option>
                  <option value="before">无限前</option>
                </select>
              </label>
              <label className="yc-field yc-field-grow">
                <span>年</span>
                <input
                  type="number"
                  min={1}
                  step={1}
                  inputMode="numeric"
                  value={infiniteForm.year}
                  onChange={(e) => updateInfinite({ year: e.target.value })}
                  placeholder="如 423"
                />
              </label>
            </div>
            <div className="yc-field-row">
              <label className="yc-field">
                <span>月</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  step={1}
                  inputMode="numeric"
                  value={infiniteForm.month}
                  onChange={(e) => updateInfinite({ month: e.target.value })}
                  placeholder="1-12"
                />
              </label>
              <label className="yc-field">
                <span>日</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  step={1}
                  inputMode="numeric"
                  value={infiniteForm.day}
                  onChange={(e) => updateInfinite({ day: e.target.value })}
                  placeholder="1-31"
                />
              </label>
            </div>
            <button type="submit" className="yc-submit-btn">
              <i className="fa fa-exchange" aria-hidden="true"></i> 换算
            </button>
          </form>
          <ResultPanel result={infiniteResult} />
          <p className="yc-formula">无限 N 年 = 公元 (1603 + N) 年</p>
        </section>

        <section className="yc-card" aria-labelledby="yc-gregorian-title">
          <h2 className="yc-card-title" id="yc-gregorian-title">
            <i className="fa fa-long-arrow-left" aria-hidden="true"></i> 公元历 → 无限历
          </h2>
          <p className="yc-card-desc">公元前请选择「公元前」并填写正数年份；公元纪年没有 0 年。</p>
          <form className="yc-form" onSubmit={submitGregorian}>
            <div className="yc-field-row">
              <label className="yc-field">
                <span>纪年</span>
                <select value={gregorianForm.era} onChange={(e) => updateGregorian({ era: e.target.value as GregorianEra })}>
                  <option value="ce">公元</option>
                  <option value="bce">公元前</option>
                </select>
              </label>
              <label className="yc-field yc-field-grow">
                <span>年</span>
                <input
                  type="number"
                  min={1}
                  step={1}
                  inputMode="numeric"
                  value={gregorianForm.year}
                  onChange={(e) => updateGregorian({ year: e.target.value })}
                  placeholder="如 2026"
                />
              </label>
            </div>
            <div className="yc-field-row">
              <label className="yc-field">
                <span>月</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  step={1}
                  inputMode="numeric"
                  value={gregorianForm.month}
                  onChange={(e) => updateGregorian({ month: e.target.value })}
                  placeholder="1-12"
                />
              </label>
              <label className="yc-field">
                <span>日</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  step={1}
                  inputMode="numeric"
                  value={gregorianForm.day}
                  onChange={(e) => updateGregorian({ day: e.target.value })}
                  placeholder="1-31"
                />
              </label>
            </div>
            <button type="submit" className="yc-submit-btn">
              <i className="fa fa-exchange" aria-hidden="true"></i> 换算
            </button>
          </form>
          <ResultPanel result={gregorianResult} />
          <p className="yc-formula">公元 1603 年及以前 = 无限前 (1604 - 公元年) 年</p>
        </section>
      </div>

      <section className="yc-rules" aria-labelledby="yc-rules-title">
        <h2 className="yc-rules-title" id="yc-rules-title">
          <i className="fa fa-book" aria-hidden="true"></i> 换算规则
        </h2>
        <ul className="yc-rules-list">
          <li>无限元年 = 公元 1604 年；无限 N 年 = 公元 (1603 + N) 年。</li>
          <li>公元 1603 年及以前记为「无限前」：无限前 1 年 = 公元 1603 年。</li>
          <li>两套纪年都不存在 0 年：无限前 1 年之后直接是无限元年；公元前 1 年之后直接是公元 1 年。</li>
          <li>2 月 29 日只在闰年存在；目标年份不是闰年时会给出提示，不输出无效日期。</li>
          <li>年、月、日之外不改变月日，仅在换算年份时同步提示该日期在目标年是否有效。</li>
        </ul>
      </section>
    </div>
  );
}

