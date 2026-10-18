/** 浏览器端统一 API base：环境变量 + /ov2/api（默认同源）。 */
export const API_BASE = `${process.env.NEXT_PUBLIC_API_BASE || ""}/ov2/api`;

/** 服务端（SSR/SEO/sitemap）统一 API base：API_TARGET + /ov2/api。 */
export const SERVER_API_BASE = `${process.env.API_TARGET || "http://127.0.0.1:8090"}/ov2/api`;

/** 拼接浏览器端 API URL。 */
export function apiUrl(path: string): string {
  if (!path) return API_BASE;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

/** 拼接服务端 API URL。 */
export function serverApiUrl(path: string): string {
  if (!path) return SERVER_API_BASE;
  return `${SERVER_API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
