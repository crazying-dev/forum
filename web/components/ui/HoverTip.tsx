"use client";

// 悬浮气泡提示（非原生 title）：hover/focus 显示，样式走 tokens（含夜间模式）
import { useId, useState } from "react";

export default function HoverTip({
  text,
  children,
  className = "",
}: {
  text: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [show, setShow] = useState(false);
  const id = useId();
  return (
    <span
      className={`hover-tip-wrap ${className}`}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      aria-describedby={show ? id : undefined}
    >
      {children}
      {show && (
        <span role="tooltip" id={id} className="hover-tip-bubble">
          {text}
        </span>
      )}
    </span>
  );
}
