"use client";

import { prefixBadgeColor } from "@/lib/constants";
import { PrefixBadgeSvg } from "../PrefixBadge";

/**
 * 头像右下角前缀徽章（HG/YJ 三角 SVG）。
 * 与 UserAvatar 配合使用：同一角落体系里 VIP 优先靠角，前缀徽标向左并排。
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

/** 头像右下角 VIP 徽章（内置 /assets/img/vip.svg，替代外链图标与 fa-diamond） */
export function CornerVipBadge({ vip }: { vip?: boolean }) {
  if (!vip) return null;
  return (
    <span className="avatar-corner-badge avatar-corner-badge-vip">
      <img src="/assets/img/vip.svg" alt="VIP" title="VIP 会员" loading="lazy" />
    </span>
  );
}