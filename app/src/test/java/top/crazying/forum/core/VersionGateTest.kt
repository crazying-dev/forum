package top.crazying.forum.core

import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 最低版本闸门（HTTP 426 / `VERSION_TOO_LOW`）的 JVM 单测。
 *
 * 只覆盖纯 Kotlin 逻辑：客户端标识头常量、[Constants.isVersionTooLow] 判定，
 * 以及给 Request 统一加头的 [Constants.applyClientHeaders]。
 * 全程不发起网络请求，也不触碰 Android / org.json。
 */
class VersionGateTest {

    private fun request(): Request =
        Request.Builder().url("https://www.yjlt.top/api/posts").build()

    @Test
    fun platformConstantIsAndroid() {
        assertEquals("android", Constants.CLIENT_PLATFORM)
    }

    @Test
    fun clientHeadersCarryPlatformAndVersion() {
        assertEquals("android", Constants.CLIENT_HEADERS["X-Client-Platform"])
        assertEquals(Constants.APP_VERSION, Constants.CLIENT_HEADERS["X-Client-Version"])
    }

    @Test
    fun clientUaTracksAppVersion() {
        assertEquals("CrForum-Android/" + Constants.APP_VERSION, Constants.CLIENT_UA)
    }

    @Test
    fun versionCodeConstantMatchesServer() {
        assertEquals("VERSION_TOO_LOW", Constants.VERSION_TOO_LOW_CODE)
    }

    @Test
    fun status426AlwaysTriggersGate() {
        assertTrue(Constants.isVersionTooLow(426, null))
        assertTrue(Constants.isVersionTooLow(426, "anything"))
    }

    @Test
    fun versionTooLowCodeTriggersGate() {
        assertTrue(Constants.isVersionTooLow(200, "VERSION_TOO_LOW"))
        assertTrue(Constants.isVersionTooLow(400, " VERSION_TOO_LOW "))
    }

    @Test
    fun ordinaryFailuresDoNotTriggerGate() {
        assertFalse(Constants.isVersionTooLow(200, null))
        assertFalse(Constants.isVersionTooLow(401, "UNAUTHORIZED"))
        assertFalse(Constants.isVersionTooLow(500, "SERVER_ERROR"))
    }

    @Test
    fun applyClientHeadersAddsHeadersWithoutMutatingSource() {
        val original = request()
        val decorated = Constants.applyClientHeaders(original)
        assertEquals("android", decorated.header("X-Client-Platform"))
        assertEquals(Constants.APP_VERSION, decorated.header("X-Client-Version"))
        assertNull("不得改动原请求", original.header("X-Client-Platform"))
    }

    @Test
    fun applyingTwiceDoesNotDuplicateHeaders() {
        val once = Constants.applyClientHeaders(request())
        val twice = Constants.applyClientHeaders(once)
        assertEquals(
            listOf(Constants.CLIENT_PLATFORM),
            twice.headers("X-Client-Platform"),
        )
    }

    @Test
    fun interceptorIsAvailable() {
        assertNotNull(Constants.clientHeaderInterceptor())
    }
}
