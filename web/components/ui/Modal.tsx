"use client";

import { ReactNode, useEffect, useRef } from "react";

// 滚动锁计数：支持弹窗叠加（如资料弹窗内再打开日历），全部关闭后才恢复页面滚动。
// 模块级计数用 globalThis 保存，避免 HMR / 多 bundle 场景下丢失。
const lockState = globalThis as unknown as {
  __yjModalLockCount?: number;
  /** 弹窗栈：仅栈顶弹窗响应 ESC（避免叠加弹窗被同时关闭） */
  __yjModalStack?: symbol[];
};
function lockBodyScroll() {
  lockState.__yjModalLockCount = (lockState.__yjModalLockCount || 0) + 1;
  document.body.style.overflow = "hidden";
}
function unlockBodyScroll() {
  lockState.__yjModalLockCount = Math.max(0, (lockState.__yjModalLockCount || 0) - 1);
  if (lockState.__yjModalLockCount === 0) document.body.style.overflow = "";
}

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
  // onClose 常为内联函数：用 ref 保持最新，避免 effect 重跑导致弹窗栈顺序变化
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    if (lockScroll) lockBodyScroll();
    const stack = lockState.__yjModalStack || (lockState.__yjModalStack = []);
    const id = Symbol("modal");
    stack.push(id);
    const onKey = (e: KeyboardEvent) => {
      // 只有最后打开（栈顶）的弹窗处理 ESC
      if (e.key === "Escape" && stack[stack.length - 1] === id) onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = stack.lastIndexOf(id);
      if (i >= 0) stack.splice(i, 1);
      if (lockScroll) unlockBodyScroll();
    };
  }, [open, lockScroll]);

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
