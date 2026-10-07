package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 网页端登录（[WebAuth]）的纯逻辑用例。
 *
 * 这些函数是「内置 WebView 登录 → 把 Cookie 搬进 App 会话」链路的地基：
 * 只要它们错了，用户就会卡在「网页里明明登录成功了，App 却没登录」。
 */
class WebAuthTest {

    @Test
    fun loginUrlIsAbsoluteAndForcesLoginMode() {
        assertEquals(
            "https://www.yjlt.top/auth?mode=login",
            WebAuth.loginUrl("https://www.yjlt.top"),
        )
        // 末尾斜杠 / 空白不能拼出双斜杠
        assertEquals(
            "https://www.yjlt.top/auth?mode=login",
            WebAuth.loginUrl("  https://www.yjlt.top/  "),
        )
    }

    @Test
    fun siteUrlTrimsTrailingSlash() {
        assertEquals("https://www.yjlt.top", WebAuth.siteUrl("https://www.yjlt.top/"))
        assertEquals("", WebAuth.siteUrl(""))
    }

    @Test
    fun cookiePairsSplitsOnSemicolonAndTrims() {
        assertEquals(
            listOf("token" to "abc", "ID" to "RL001"),
            WebAuth.cookiePairs("token=abc; ID=RL001"),
        )
        // 多余空白 / 空段 / 垃圾段都应被忽略
        assertEquals(
            listOf("token" to "abc"),
            WebAuth.cookiePairs("  token = abc ; ; garbage ; =nope"),
        )
    }

    @Test
    fun cookiePairsToleratesMissingInput() {
        assertTrue(WebAuth.cookiePairs(null).isEmpty())
        assertTrue(WebAuth.cookiePairs("").isEmpty())
        assertTrue(WebAuth.cookiePairs("   ").isEmpty())
    }

    @Test
    fun cookiePairsDropsEmptyValue() {
        // 登出时服务端会下发 token=; —— 空值不算登录态
        assertEquals(emptyList<Pair<String, String>>(), WebAuth.cookiePairs("token=; ID="))
    }

    @Test
    fun hasSessionRequiresBothCookies() {
        assertTrue(WebAuth.hasSession("token=abc; ID=RL001"))
        assertFalse("只有 token 不算已登录", WebAuth.hasSession("token=abc"))
        assertFalse("只有 ID 不算已登录", WebAuth.hasSession("ID=RL001"))
        assertFalse(WebAuth.hasSession(null))
        assertFalse(WebAuth.hasSession(""))
    }

    @Test
    fun hasSessionIgnoresOtherCookies() {
        assertFalse(WebAuth.hasSession("sessionid=xyz; csrftoken=q; theme=dark"))
        assertTrue(WebAuth.hasSession("sessionid=xyz; token=t; ID=RL001; theme=dark"))
    }

    @Test
    fun cookieNamesAreCaseSensitive() {
        // 服务端用的是小写 token 与大写 ID，不能宽松匹配
        assertFalse(WebAuth.hasSession("Token=abc; ID=RL001"))
        assertFalse(WebAuth.hasSession("token=abc; id=RL001"))
    }
}
