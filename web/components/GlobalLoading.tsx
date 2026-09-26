"use client";

/**
 * 全局加载动图：呼吸的「妖」字圆点 Logo + 三点脉冲 + 文案。
 * 用于路由切换（app/loading.tsx）与各列表加载态（ListLoading）。
 */
export default function GlobalLoading({
  size = 76,
  text = "加载中…",
  className = "",
}: {
  size?: number;
  text?: string;
  className?: string;
}) {
  return (
    <div className={`global-loading ${className}`.trim()} role="status" aria-live="polite">
      <div className="global-loading-logo" style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}>
        <span className="global-loading-char">妖</span>
      </div>
      <div className="global-loading-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
      {text && <div className="global-loading-text">{text}</div>}
    </div>
  );
}
