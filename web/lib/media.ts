/** 新媒体 ID：MD + 8~62 位字母数字（与后端 mediaIDPattern 保持一致）。 */
const MEDIA_ID_RE = /^MD[A-Za-z0-9]{8,62}$/;

/** 是否为新媒体 ID（旧 GridFS 的 24 位 ObjectID 返回 false）。 */
export function isMediaId(id?: string | null): boolean {
  return MEDIA_ID_RE.test((id || "").trim());
}

/**
 * 媒体直出地址：/ov2/api/media/<media_id>。
 * 旧 GridFS 文件（ObjectID）无对应 media 行，返回空串由调用方回退占位。
 */
export function mediaUrl(id?: string | null): string {
  const v = (id || "").trim();
  return isMediaId(v) ? `/ov2/api/media/${encodeURIComponent(v)}` : "";
}

/** 会馆 logo / 介绍页封面等：新 MD 直出，旧 GridFS 走管理端兼容代理 */
export function guildImageUrl(
  fileId: string | null | undefined,
  guildUuid: string | null | undefined,
  kind: "logo" | "intro-images" | "leader-images" = "logo",
  version?: number
): string {
  const media = mediaUrl(fileId);
  if (media) return media;
  const id = (fileId || "").trim();
  const uuid = (guildUuid || "").trim();
  if (!id || !uuid) return "";
  const base =
    kind === "logo"
      ? `/guild-img/guilds/${encodeURIComponent(uuid)}/logo`
      : `/guild-img/guilds/${encodeURIComponent(uuid)}/${kind}/${encodeURIComponent(id)}`;
  return version && version > 0 ? `${base}?v=${version}` : base;
}
