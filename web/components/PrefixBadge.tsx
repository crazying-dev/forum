"use client";

/** 前缀徽章 V 形 SVG（HG/YJ 三角），头像右下角标 / 其他场景共用 */
export function PrefixBadgeSvg({ color }: { color: string }) {
  return (
    <svg viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="11" cy="11" r="11" fill={color} />
      <path d="M11 15L6 7H8L11 11L14 7H16L11 15Z" fill="white" />
    </svg>
  );
}
