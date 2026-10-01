"use client";

import { ReactNode, useEffect } from "react";

/**
 * 通用居中弹窗(overlay + card + close + ESC 关闭)。
 * 默认样式类为 donate-*(视觉 1:1);可通过 className 覆盖(如 FollowListModal 的 follow-list-*)。
 */
export default function Modal({
  open,
  onClose,
  children,
  className = "donate-modal",
  overlayClassName = "donate-overlay",
  cardClassName = "donate-card",
  closeClassName = "donate-close",
  cardStyle,
  closeable = true,
  lockScroll = false,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  overlayClassName?: string;
  cardClassName?: string;
  closeClassName?: string;
  cardStyle?: React.CSSProperties;
  closeable?: boolean;
  lockScroll?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    if (lockScroll) document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (lockScroll) document.body.style.overflow = "";
    };
  }, [open, onClose, lockScroll]);

  if (!open) return null;
  return (
    <div className={className} style={{ display: "flex" }}>
      <div className={overlayClassName} onClick={onClose}></div>
      <div className={cardClassName} style={cardStyle} role="dialog" aria-modal="true">
        {closeable && (
          <button className={closeClassName} onClick={onClose} aria-label="关闭">
            &times;
          </button>
        )}
        {children}
      </div>
    </div>
  );
}
