"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * 轮播状态（会馆广场 / 会馆公告共用）：
 * - 默认约 5s 自动切换
 * - 鼠标悬停时暂停，移出后恢复
 * - 用户交互（箭头/圆点/缩略图）后冷却一段时间再恢复自动播放
 */
export function useCarousel(length: number, interval = 5000, cooldownMs = 8000) {
  const [index, setIndex] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [cooling, setCooling] = useState(false);
  const coolTimer = useRef<number | null>(null);

  const paused = hovered || cooling;

  useEffect(() => {
    if (paused || length <= 1) return;
    const t = window.setInterval(() => setIndex((i) => (i + 1) % length), interval);
    return () => window.clearInterval(t);
  }, [paused, length, interval]);

  useEffect(() => () => {
    if (coolTimer.current) window.clearTimeout(coolTimer.current);
  }, []);

  const cool = useCallback(() => {
    setCooling(true);
    if (coolTimer.current) window.clearTimeout(coolTimer.current);
    coolTimer.current = window.setTimeout(() => setCooling(false), cooldownMs);
  }, [cooldownMs]);

  const go = useCallback(
    (delta: number) => {
      if (length <= 0) return;
      setIndex((i) => (i + delta + length) % length);
      cool();
    },
    [length, cool]
  );

  const jump = useCallback(
    (i: number) => {
      setIndex(i);
      cool();
    },
    [cool]
  );

  // 悬停事件：挂到轮播容器实现「悬停暂停 / 移出恢复」；useMemo 保证引用稳定，避免每次渲染生成新对象
  const hoverProps = useMemo(
    () => ({
      onMouseEnter: () => setHovered(true),
      onMouseLeave: () => setHovered(false),
    }),
    []
  );

  // 返回：当前下标（数量变化时自动回到合法范围）、按步切换、跳转指定下标、悬停事件（挂到轮播容器）
  const safeIndex = length > 0 ? index % length : 0;

  return { index: safeIndex, go, jump, hoverProps };
}
