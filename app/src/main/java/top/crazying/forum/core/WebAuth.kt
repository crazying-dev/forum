package top.crazying.forum.core

/**
 * 网页端登录所需的**纯逻辑**（可 JVM 单测，不依赖 Android 运行时）。
 *
 * 服务端会话就是 **Cookie 会话**：登录成功后下发 `token` + `ID` 两个 HttpOnly
 * Cookie（见 `forum/config.py` 的 TOKEN_COOKIE_NAME / ID_COOKIE_NAME）。
 *
 * 所谓「通过网页端登录」，就是让用户在 App 内置 WebView 里走一遍站点的真实登录页
 * （`/auth?mode=login`）——官方 Turnstile 在真实网页里渲染，不存在内嵌承载页的
 * 层级 / 命中区问题——登录成功后把 WebView 的 Cookie 原样搬进 App 的 OkHttp
 * CookieJar，会话即完成迁移，其余接口照常走原生请求。
 */
object WebAuth {

    /** 站点登录/注册/找回密码统一入口（`forum/api/pages/__init__.py` 的 /auth）。 */
    const val AUTH_PATH = "/auth"

    /** 登录态 Cookie 名（与 `config.TOKEN_COOKIE_NAME` 同源）。 */
    const val TOKEN_COOKIE = "token"

    /** 用户 ID Cookie 名（与 `config.ID_COOKIE_NAME` 同源）。 */
    const val ID_COOKIE = "ID"

    /** 登录页绝对地址：`<base>/auth?mode=login`。 */
    fun loginUrl(baseUrl: String): String =
        (baseUrl ?: "").trim().trimEnd('/') + AUTH_PATH + "?mode=login"

    /** 站点根地址（用于 CookieManager 的查询 / 注入）。 */
    fun siteUrl(baseUrl: String): String = (baseUrl ?: "").trim().trimEnd('/')

    /**
     * `CookieManager.getCookie(url)` 的 `name=value; name2=value2` → 键值对列表。
     *
     * 容忍多余空白、空段、无 `=` 的垃圾段与空值（服务端登出时会下发 `token=;`）。
     */
    fun cookiePairs(header: String?): List<Pair<String, String>> {
        val raw = header ?: return emptyList()
        if (raw.isBlank()) return emptyList()
        val out = ArrayList<Pair<String, String>>()
        for (part in raw.split(';')) {
            val seg = part.trim()
            if (seg.isEmpty()) continue
            val i = seg.indexOf('=')
            if (i <= 0) continue
            val name = seg.substring(0, i).trim()
            val value = seg.substring(i + 1).trim()
            if (name.isEmpty() || value.isEmpty()) continue
            out.add(name to value)
        }
        return out
    }

    /** Cookie 头里是否已含完整登录态（`token` 与 `ID` 同时存在）。 */
    fun hasSession(header: String?): Boolean {
        val names = cookiePairs(header).map { it.first }
        return names.contains(TOKEN_COOKIE) && names.contains(ID_COOKIE)
    }
}
