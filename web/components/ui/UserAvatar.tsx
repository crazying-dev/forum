"use client";

import { useState, type CSSProperties } from "react";

import { prefixBadgeColor } from "@/lib/constants";
import { CornerPrefixBadge } from "./CornerBadge";

const DEFAULT_AVATAR = "/static/img/avatars/LuoXiaoHei1.png";

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
  imgWidth,
  imgHeight,
  imgStyle,
  loading = "lazy",
}: {
  src?: string | null;
  alt?: string;
  imgClassName?: string;
  fallbackClassName?: string;
  imgId?: string;
  userId?: string | null;
  imgWidth?: number;
  imgHeight?: number;
  imgStyle?: CSSProperties;
  loading?: "lazy" | "eager";
}) {
  // 旧头像文件可能已缺失：先回退到本地默认头像；默认头像也失败时退化为 fa-user 图标。
  const [failure, setFailure] = useState<{ src: string; stage: 1 | 2 } | null>(null);
  const stage = src && failure?.src === src ? failure.stage : 0;
  const effectiveSrc = src ? (stage === 2 ? null : stage === 1 ? DEFAULT_AVATAR : src) : null;

  const handleError = () => {
    if (!src) return;
    if (stage === 0) setFailure({ src, stage: src === DEFAULT_AVATAR ? 2 : 1 });
    else if (stage === 1) setFailure({ src, stage: 2 });
  };

  const body = effectiveSrc ? (
    <img
      src={effectiveSrc}
      alt={alt}
      loading={loading}
      width={imgWidth}
      height={imgHeight}
      style={imgStyle}
      className={`avatar-round${imgClassName ? ` ${imgClassName}` : ""}`}
      id={imgId}
      onError={handleError}
    />
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
