"use client";

import { prefixBadgeColor } from "@/lib/constants";
import { CornerPrefixBadge } from "./CornerBadge";

/**
 * 用户头像(含 fa-user fallback)。
 * 传入 userId 时会在头像右下角展示前缀角标(HG/YJ)；
 * 无角标时仍只渲染 img / fallback 本体，外层容器(wrapper/Link)由调用方决定。
 * 注意：角标需要容器不裁剪溢出(见 app/styles/ui-fixes.css 头像容器 overflow: visible 规则)。
 */
export function UserAvatar({
  src,
  alt = "",
  imgClassName = "",
  fallbackClassName = "avatar-fallback",
  imgId,
  userId,
}: {
  src?: string | null;
  alt?: string;
  imgClassName?: string;
  fallbackClassName?: string;
  imgId?: string;
  userId?: string | null;
}) {
  const body = src ? (
    <img src={src} alt={alt} loading="lazy" className={imgClassName || undefined} id={imgId} />
  ) : (
    <i className={`fa fa-user ${fallbackClassName}`}></i>
  );

  const corner = !!prefixBadgeColor(userId);
  if (!corner) return body;

  return (
    <span className="avatar-corner-wrap">
      {body}
      <span className="avatar-corner-badges">
        <CornerPrefixBadge userId={userId} />
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
