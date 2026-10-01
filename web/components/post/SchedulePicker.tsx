"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

/** 本地时区时间串（YYYY-MM-DDTHH:mm）工具：与发帖页 min/max、提交转换口径一致 */
const pad = (n: number) => String(n).padStart(2, "0");
const fmtDate = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;
const dateOf = (v: string) => (v ? v.slice(0, 10) : "");
const timeOf = (v: string) => (v.length >= 16 ? v.slice(11, 16) : "");

/** 同格式（月/日/时/分均补零）的本地时间串可直接按字典序比较；超界时收敛到边界 */
function clampToBounds(next: string, min: string, max: string): string {
  if (min && next < min) return min;
  if (max && next > max) return max;
  return next;
}

const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const HOURS = Array.from({ length: 24 }, (_, i) => pad(i));
const MINUTES = Array.from({ length: 12 }, (_, i) => pad(i * 5));

/**
 * 定时发布时间选择器（受控，值为本地 "YYYY-MM-DDTHH:mm"）：
 * 日期胶囊条（今天起 14 天）+ 时/分下拉 + 「更多日期」自研日历浮层；
 * 变更后若早于 min 或晚于 max 则收敛到边界，保证页面提交校验（+5 分钟 / 1 年）口径不变。
 */
export default function SchedulePicker({
  value,
  min,
  max,
  onChange,
}: {
  value: string;
  min: string;
  max: string;
  onChange: (next: string) => void;
}) {
  const today = new Date();
  const [calOpen, setCalOpen] = useState(false);
  const [calView, setCalView] = useState<{ y: number; m: number }>(() => {
    const base = dateOf(value) || dateOf(min) || fmtDate(today.getFullYear(), today.getMonth() + 1, today.getDate());
    const [y, m] = base.split("-").map(Number);
    return { y, m };
  });
  const moreRef = useRef<HTMLDivElement>(null);

  const selectedDate = dateOf(value);
  // 当前值（空值时回退 min，再回退今天）的日期/时间，作为各控件变更的基准
  const baseDate = selectedDate || dateOf(min) || fmtDate(today.getFullYear(), today.getMonth() + 1, today.getDate());
  const baseTime = timeOf(value) || timeOf(min) || "00:00";
  const hh = timeOf(value).slice(0, 2);
  const mm = timeOf(value).slice(3, 5);

  // 未来 14 天胶囊：今天 / 明天 / 周X + 小字 M-D
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
    const key = fmtDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return {
      key,
      label: i === 0 ? "今天" : i === 1 ? "明天" : `周${WEEK[d.getDay()]}`,
      sub: `${d.getMonth() + 1}-${d.getDate()}`,
      selected: key === selectedDate,
    };
  });
  const inCapsuleRange = days.some((d) => d.selected);
  // 当前值不在 14 天胶囊内：无胶囊高亮，「更多日期」按钮回显所选日期
  const moreLabel = selectedDate && !inCapsuleRange ? `更多日期 · ${selectedDate.slice(5)}` : "更多日期";

  // 分钟选项：5 分钟步进；当前分钟不在步进上时追加当前值，避免静默改值
  const minuteOptions = useMemo(() => {
    const opts = [...MINUTES];
    if (mm && !opts.includes(mm)) opts.push(mm);
    return opts.sort();
  }, [mm]);

  // 点击外部 / ESC 关闭日历浮层
  useEffect(() => {
    if (!calOpen) return;
    const onClick = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setCalOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCalOpen(false);
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [calOpen]);

  const emit = (dateStr: string, timeStr: string) => onChange(clampToBounds(`${dateStr}T${timeStr}`, min, max));

  const pickDay = (dateStr: string) => emit(dateStr, baseTime);
  const pickHour = (h: string) => emit(baseDate, `${h}:${mm || baseTime.slice(3)}`);
  const pickMinute = (m: string) => emit(baseDate, `${hh || baseTime.slice(0, 2)}:${m}`);

  const toggleCalendar = () => {
    if (!calOpen) {
      const base = selectedDate || baseDate;
      const [y, m] = base.split("-").map(Number);
      setCalView({ y, m });
    }
    setCalOpen(!calOpen);
  };

  const stepCalMonth = (delta: number) => {
    setCalView((v) => {
      let m = v.m + delta;
      let y = v.y;
      if (m < 1) {
        m = 12;
        y -= 1;
      }
      if (m > 12) {
        m = 1;
        y += 1;
      }
      return { y, m };
    });
  };

  // 日历网格：超出 [min, max] 的日期禁用
  const minDate = dateOf(min);
  const maxDate = dateOf(max);
  const firstWeekday = new Date(calView.y, calView.m - 1, 1).getDay();
  const daysInMonth = new Date(calView.y, calView.m, 0).getDate();
  const calCells: ReactNode[] = [];
  for (let i = 0; i < firstWeekday; i++) calCells.push(<span className="post-schedule-cal-empty" key={`e${i}`} />);
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = fmtDate(calView.y, calView.m, d);
    const disabled = (!!minDate && ds < minDate) || (!!maxDate && ds > maxDate);
    calCells.push(
      <button
        type="button"
        key={d}
        className={`post-schedule-cal-day${ds === selectedDate ? " selected" : ""}`}
        disabled={disabled}
        onClick={() => {
          pickDay(ds);
          setCalOpen(false);
        }}
      >
        {d}
      </button>
    );
  }

  return (
    <div className="post-schedule-controls">
      {/* 日期胶囊条：14 天横向滚动 */}
      <div className="post-schedule-days">
        {days.map((d) => (
          <button
            type="button"
            key={d.key}
            className={`post-schedule-day${d.selected ? " active" : ""}`}
            onClick={() => pickDay(d.key)}
          >
            <span className="post-schedule-day-label">{d.label}</span>
            <span className="post-schedule-day-sub">{d.sub}</span>
          </button>
        ))}
      </div>

      {/* 小时 / 分钟下拉（分钟 5 分钟步进） */}
      <div className="post-schedule-time">
        <span className="post-schedule-select-wrap">
          <select className="post-schedule-select" value={hh} aria-label="小时" onChange={(e) => pickHour(e.target.value)}>
            {!hh && (
              <option value="" disabled>
                时
              </option>
            )}
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
          <i className="fa fa-angle-down post-schedule-select-caret"></i>
        </span>
        <span className="post-schedule-time-sep">:</span>
        <span className="post-schedule-select-wrap">
          <select className="post-schedule-select" value={mm} aria-label="分钟" onChange={(e) => pickMinute(e.target.value)}>
            {!mm && (
              <option value="" disabled>
                分
              </option>
            )}
            {minuteOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <i className="fa fa-angle-down post-schedule-select-caret"></i>
        </span>
      </div>

      {/* 更多日期：自研日历浮层 */}
      <div className="post-schedule-more" ref={moreRef}>
        <button type="button" className={`post-schedule-more-btn${calOpen ? " open" : ""}`} aria-haspopup="dialog" aria-expanded={calOpen} onClick={toggleCalendar}>
          <i className="fa fa-calendar"></i> {moreLabel}
        </button>
        {calOpen && (
          <div className="post-schedule-cal">
            <div className="post-schedule-cal-head">
              <button type="button" className="post-schedule-cal-nav" onClick={() => stepCalMonth(-1)} aria-label="上个月">
                <i className="fa fa-chevron-left"></i>
              </button>
              <span className="post-schedule-cal-title">
                {calView.y}年{calView.m}月
              </span>
              <button type="button" className="post-schedule-cal-nav" onClick={() => stepCalMonth(1)} aria-label="下个月">
                <i className="fa fa-chevron-right"></i>
              </button>
            </div>
            <div className="post-schedule-cal-grid">
              {WEEK.map((w) => (
                <span key={w} className="post-schedule-cal-week">
                  {w}
                </span>
              ))}
              {calCells}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
