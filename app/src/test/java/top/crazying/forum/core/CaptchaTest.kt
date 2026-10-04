package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * 滑块拼图人机验证的 JVM 单测。
 *
 * 只覆盖纯 Kotlin 逻辑：错误码 / 受保护端点表 / data URL 解析 / 拖拽坐标映射，
 * 以及「业务流程确实调了 askCaptcha()」的源码扫描。
 * 全程不发起网络请求，也不触碰 Android 运行时与 Compose。
 */
class CaptchaTest {

    // ────────────────── 与服务端的约定 ──────────────────

    @Test
    fun requiredCodeMatchesServer() {
        assertEquals("CAPTCHA_REQUIRED", Captcha.REQUIRED_CODE)
    }

    @Test
    fun challengeAndVerifyPathsMatchServer() {
        assertEquals("/api/captcha/challenge", Captcha.CHALLENGE_PATH)
        assertEquals("/api/captcha/verify", Captcha.VERIFY_PATH)
    }

    @Test
    fun bodyFieldNamesMatchServer() {
        assertEquals("captcha_token", Captcha.FIELD_TOKEN)
        assertEquals("captcha_x", Captcha.FIELD_X)
    }

    @Test
    fun isRequiredOnlyForCaptchaCode() {
        assertTrue(Captcha.isRequired("CAPTCHA_REQUIRED"))
        assertTrue(Captcha.isRequired(" CAPTCHA_REQUIRED "))
        assertFalse(Captcha.isRequired(null))
        assertFalse(Captcha.isRequired(""))
        assertFalse(Captcha.isRequired("VERSION_TOO_LOW"))
        assertFalse(Captcha.isRequired("UNAUTHORIZED"))
    }

    @Test
    fun protectedEndpointsMatchServer() {
        val expected = listOf(
            "/api/user/login",
            "/api/user/register",
            "/api/user/delete",
            "/api/email/send-register-code",
            "/api/email/send-code-reset-password",
            "/api/email/reset-password-by-code",
            "/api/email/send-change-password-code",
            "/api/email/send-change-email-code",
            "/api/email/send-change-email-old-code",
            "/api/email/send-delete-account-code",
        )
        assertEquals(expected.size, Captcha.PROTECTED_ENDPOINTS.size)
        assertEquals(expected, Captcha.PROTECTED_ENDPOINTS)
    }

    @Test
    fun terminalStepsAreNotProtected() {
        // 服务端只保护「发验证码」这一步，改密 / 换绑的终步不带人机验证。
        assertFalse(Captcha.PROTECTED_ENDPOINTS.contains("/api/user/password"))
        assertFalse(Captcha.PROTECTED_ENDPOINTS.contains("/api/user/email"))
    }

    // ────────────────── data URL 解析 ──────────────────

    @Test
    fun dataUrlPayloadStripsPrefix() {
        assertEquals("AAAA", Captcha.dataUrlPayload("data:image/png;base64,AAAA"))
        assertEquals("AAAA", Captcha.dataUrlPayload("  data:image/png;base64,AAAA  "))
    }

    @Test
    fun dataUrlPayloadHandlesBareAndEmptyValues() {
        // 无逗号时整串即载荷（兼容服务端以后直接给裸 base64）
        assertEquals("AAAA", Captcha.dataUrlPayload("AAAA"))
        assertEquals("", Captcha.dataUrlPayload(""))
        assertEquals("", Captcha.dataUrlPayload("data:image/png;base64,"))
    }

    @Test
    fun decodeRejectsEmptyPayload() {
        assertNull(Captcha.decodeDataUrl(""))
        assertNull(Captcha.decodeDataUrl("data:image/png;base64,"))
    }

    // ────────────────── 拖拽坐标映射 ──────────────────

    @Test
    fun pieceXIsLinearAndClamped() {
        val travel = 280f
        val maxPieceX = 270f
        assertEquals(0f, Captcha.pieceXFromDrag(0f, travel, maxPieceX), 0.001f)
        assertEquals(270f, Captcha.pieceXFromDrag(travel, travel, maxPieceX), 0.001f)
        assertEquals(135f, Captcha.pieceXFromDrag(travel / 2f, travel, maxPieceX), 0.001f)
        // 越界一律夹到边界
        assertEquals(270f, Captcha.pieceXFromDrag(9999f, travel, maxPieceX), 0.001f)
        assertEquals(0f, Captcha.pieceXFromDrag(-50f, travel, maxPieceX), 0.001f)
    }

    @Test
    fun handleXRoundTripsThroughPieceX() {
        val travel = 280f
        val maxPieceX = 270f
        for (d in listOf(0f, 37f, 140f, 279f, 280f)) {
            val pieceX = Captcha.pieceXFromDrag(d, travel, maxPieceX)
            val back = Captcha.handleXFromPiece(pieceX, travel, maxPieceX)
            assertEquals(d, back, 0.01f)
        }
    }

    @Test
    fun degenerateGeometryDoesNotCrash() {
        // 舞台过窄 / 参数缺失时不能除零，统一回 0。
        assertEquals(0f, Captcha.pieceXFromDrag(10f, 0f, 0f), 0.001f)
        assertEquals(0f, Captcha.handleXFromPiece(10f, 0f, 0f), 0.001f)
        assertEquals(0f, Captcha.pieceXFromDrag(10f, 100f, 0f), 0.001f)
    }

    // ────────────────── 接入点回归 ──────────────────

    @Test
    fun callSitesAskForCaptcha() {
        val root = sourceRoot()
        assertTrue("找不到源码根目录（期望 <repo>/app/src/main/java/top/crazying/forum）", root != null)
        val screens = listOf(
            "ui/screens/AuthScreen.kt",
            "ui/screens/ProfileEditScreen.kt",
            "ui/screens/DeleteAccountScreen.kt",
        )
        for (rel in screens) {
            val f = File(root, rel)
            assertTrue("缺少源文件：$rel", f.exists())
            assertTrue("$rel 未接入 askCaptcha()", f.readText().contains("askCaptcha()"))
        }
    }

    @Test
    fun apiMergesCaptchaTokenIntoBodies() {
        val root = sourceRoot() ?: return
        val api = File(root, "core/Api.kt")
        assertTrue("缺少源文件：core/Api.kt", api.exists())
        val text = api.readText()
        // 8 个受保护接口 + challenge/verify 自身不带 token 合并，故至少 8 处。
        val merges = Regex("Captcha\\.withToken\\(").findAll(text).count()
        assertTrue("受保护接口未接入 Captcha.withToken（当前 $merges 处）", merges >= 8)
        assertTrue(text.contains("Captcha.CHALLENGE_PATH"))
        assertTrue(text.contains("Captcha.VERIFY_PATH"))
    }

    /** 从工作目录（Gradle 单测默认是 `app/`）向上找 `app/src/main/java/top/crazying/forum`。 */
    private fun sourceRoot(): File? {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "app/src/main/java/top/crazying/forum")
            if (candidate.isDirectory) return candidate
            dir = dir.parentFile
        }
        return null
    }
}
