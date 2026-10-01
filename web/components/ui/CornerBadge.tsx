"use client";

import { prefixBadgeColor } from "@/lib/constants";
import { PrefixBadgeSvg } from "../PrefixBadge";

/**
 * 头像右下角前缀徽章（HG/YJ 三角 SVG）。
 * 与 UserAvatar 配合使用：渲染在头像右下角角标体系中。
 */
export function CornerPrefixBadge({ userId }: { userId?: string | null }) {
  const color = prefixBadgeColor(userId);
  if (!color) return null;
  return (
    <span className="avatar-corner-badge avatar-corner-badge-prefix">
      <PrefixBadgeSvg color={color} />
    </span>
  );
}
