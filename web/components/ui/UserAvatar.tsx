"use client";

import { prefixBadgeColor } from "@/lib/constants";
import { CornerPrefixBadge, CornerVipBadge } from "./CornerBadge";

/**
 * 用户头像(含 fa-user fallback)。
 * 传入 userId / vip 时会在头像右下角展示角标(VIP 优先靠角，前缀徽标向左并排)；
 * 无角标时仍只渲染 img / fallback 本体，外层容器(wrapper/Link)由调用方决定。
 * 注意：角标需要容器不裁剪溢出(见 globals.css 头像容器 overflow: visible 规则)。
 */
export function UserAvatar({
  src,
  alt = "",
  imgClassName = "",
  fallbackClassName = "avatar-fallback",
  imgId,
  userId,
  vip = false,
}: {
  src?: string | null;
  alt?: string;
  imgClassName?: string;
  fallbackClassName?: string;
  imgId?: string;
  userId?: string | null;
  vip?: boolean;
}) {
  const body = src ? (
    <img src={src} alt={alt} loading="lazy" className={imgClassName || undefined} id={imgId} />
  ) : (
    <i className={`fa fa-user ${fallbackClassName}`}></i>
  );

  const corner = !!prefixBadgeColor(userId) || !!vip;
  if (!corner) return body;

  return (
    <span className="avatar-corner-wrap">
      {body}
      <span className="avatar-corner-badges">
        <CornerPrefixBadge userId={userId} />
        <CornerVipBadge vip={vip} />
      </span>
    </span>
  );
}

/**
 * 用户名(不含外层元素/链接,由调用方包装)。
 * 徽标已统一改为头像右下角展示(见 UserAvatar)，不再内联渲染。
 */
export function UserName({ name }: { name?: string | null }) {
  return <>{name || "匿名"}</>;
}
