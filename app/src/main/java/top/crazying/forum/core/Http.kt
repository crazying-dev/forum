package top.crazying.forum.core

import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

/**
 * OkHttp 的 CookieJar，把服务端的 `token` / `ID` 两个 HttpOnly Cookie 序列化到 SharedPreferences。
 *
 * 序列化格式：每个 Cookie 一行，字段用 `\u0001` 分隔，行间用 `\n` 分隔，
 * 字段依次为 `name / value / domain / path / expiresAt / secure`。
 *
 * 实现上有意回避了 OkHttp 内部的 `hostOnly` 字段（不同大版本可读性不同），
 * 重建时统一用 `domain(...)`；对 `www.yjlt.top` 这种单主机站点行为完全一致。
 */
class PrefsCookieJar(private val prefs: Prefs) : CookieJar {

    private val lock = Any()
    private val store = LinkedHashMap<String, Cookie>()

    init {
        load()
    }

    private fun keyOf(c: Cookie): String = c.name + SEP + c.domain + SEP + c.path

    private fun load() {
        synchronized(lock) {
            store.clear()
            val raw = prefs.cookieStore
            if (raw.isBlank()) return
            for (line in raw.split(LINE)) {
                if (line.isBlank()) continue
                val f = line.split(SEP)
                if (f.size < 6) continue
                val cookie = try {
                    val builder = Cookie.Builder()
                        .name(f[0])
                        .value(f[1])
                        .domain(f[2])
                        .path(f[3])
                    val expires = f[4].toLongOrNull() ?: 0L
                    if (expires > 0L) builder.expiresAt(expires)
                    if (f[5] == "1") builder.secure()
                    builder.build()
                } catch (e: Exception) {
                    null
                } ?: continue
                store[keyOf(cookie)] = cookie
            }
        }
    }

    private fun save() {
        val sb = StringBuilder()
        for (c in store.values) {
            if (sb.isNotEmpty()) sb.append(LINE)
            sb.append(c.name).append(SEP)
                .append(c.value).append(SEP)
                .append(c.domain).append(SEP)
                .append(c.path).append(SEP)
                .append(c.expiresAt).append(SEP)
                .append(if (c.secure) "1" else "0")
        }
        prefs.cookieStore = sb.toString()
    }

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        synchronized(lock) {
            if (cookies.isEmpty()) return
            val now = System.currentTimeMillis()
            for (c in cookies) {
                if (c.expiresAt < now) store.remove(keyOf(c)) else store[keyOf(c)] = c
            }
            save()
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        synchronized(lock) {
            val now = System.currentTimeMillis()
            val out = ArrayList<Cookie>(store.size)
            val it = store.values.iterator()
            while (it.hasNext()) {
                val c = it.next()
                if (c.expiresAt < now) {
                    it.remove()
                    continue
                }
                if (c.matches(url)) out.add(c)
            }
            return out
        }
    }

    /**
     * 直接写入一条 Cookie（不改动入参）。
     *
     * 用于「网页登录」：从 WebView 的 `CookieManager` 读到站点的 `token` / `ID`
     * 后搬进本 jar，后续原生请求即自带登录态。
     */
    fun put(cookie: Cookie) {
        synchronized(lock) {
            store[keyOf(cookie)] = cookie
            save()
        }
    }

    fun clear() {
        synchronized(lock) {
            store.clear()
            save()
        }
    }

    private companion object {
        const val SEP = "\u0001"
        const val LINE = "\n"
    }
}
