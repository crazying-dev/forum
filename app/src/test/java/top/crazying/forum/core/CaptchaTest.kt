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
 * 只覆盖纯 Kotlin 逻辑：错误码 / 受保护端点表 / data URL 解析 / 拖拽坐标映射 /
 * provider 归一化 / 承载页 URL 拼接 / 事件回传解析，
 * 以及「业务流程确实调了 askCaptcha()」与「弹窗接了 Turnstile 桥」的源码扫描。
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

    // ────────────────── provider（服务端下发） ──────────────────

    @Test
    fun providerConstantsMatchServer() {
        assertEquals("slider", Captcha.PROVIDER_SLIDER)
        assertEquals("turnstile", Captcha.PROVIDER_TURNSTILE)
        assertEquals("off", Captcha.PROVIDER_OFF)
        assertEquals("/captcha-embed", Captcha.EMBED_PATH)
        assertEquals("captcha:", Captcha.EVENT_PREFIX)
        assertEquals("AndroidCaptcha", Captcha.JS_BRIDGE_NAME)
    }

    @Test
    fun providerOfNormalisesAndFallsBackToSlider() {
        assertEquals(Captcha.PROVIDER_TURNSTILE, Captcha.providerOf("turnstile"))
        assertEquals(Captcha.PROVIDER_TURNSTILE, Captcha.providerOf("  Turnstile "))
        assertEquals(Captcha.PROVIDER_SLIDER, Captcha.providerOf("slider"))
        // 空 / 未知一律回退滑块（与服务端 _provider() 同口径，两边都不互信）
        assertEquals(Captcha.PROVIDER_SLIDER, Captcha.providerOf(null))
        assertEquals(Captcha.PROVIDER_SLIDER, Captcha.providerOf(""))
        assertEquals(Captcha.PROVIDER_SLIDER, Captcha.providerOf("weird"))
        for (v in listOf("off", "none", "disable", "disabled", "0", "false")) {
            assertEquals("off 同义词：$v", Captcha.PROVIDER_OFF, Captcha.providerOf(v))
        }
    }

    // ────────────────── 回退通道（Turnstile → 自研滑块） ──────────────────

    @Test
    fun challengePathForcesProviderOnlyWhenGiven() {
        assertEquals("/api/captcha/challenge", Captcha.challengePath())
        assertEquals("/api/captcha/challenge", Captcha.challengePath(""))
        assertEquals("/api/captcha/challenge", Captcha.challengePath("   "))
        assertEquals("/api/captcha/challenge", Captcha.challengePath(null))
        assertEquals("/api/captcha/challenge?provider=slider", Captcha.challengePath("slider"))
        // 归一化：大写 / 两侧空白
        assertEquals("/api/captcha/challenge?provider=slider", Captcha.challengePath("  SLIDER "))
    }

    // ────────────────── 承载页 URL 拼接 ──────────────────

    @Test
    fun embedUrlBuildsAbsoluteUrlWithQuery() {
        assertEquals(
            "https://www.yjlt.top/captcha-embed?theme=dark&lang=zh-cn&size=flexible",
            Captcha.embedUrl("https://www.yjlt.top", "/captcha-embed", "dark", "flexible"),
        )
    }

    @Test
    fun embedUrlDefaultsAreLightAndFlexible() {
        assertEquals(
            "https://www.yjlt.top/captcha-embed?theme=light&lang=zh-cn&size=flexible",
            Captcha.embedUrl("https://www.yjlt.top/", null, null, null),
        )
    }

    @Test
    fun embedUrlAcceptsAbsoluteAndProtocolRelativePaths() {
        assertEquals(
            "https://challenges.cloudflare.com/x?a=1&theme=light&lang=zh-cn&size=normal",
            Captcha.embedUrl("https://www.yjlt.top", "https://challenges.cloudflare.com/x?a=1", "light", "normal"),
        )
        assertEquals(
            "https://cdn.example.com/captcha-embed?theme=light&lang=zh-cn&size=compact",
            Captcha.embedUrl("https://www.yjlt.top", "//cdn.example.com/captcha-embed", "light", "compact"),
        )
    }

    @Test
    fun embedUrlRejectsUnknownSizeAndTheme() {
        val u = Captcha.embedUrl("https://a.b", "/e", "blue", "huge")
        assertTrue("非法 theme / size 应回退 light + flexible：$u",
            u.endsWith("?theme=light&lang=zh-cn&size=flexible"))
    }

    // ────────────────── 事件回传解析 ──────────────────

    @Test
    fun eventOfParsesKindAndPayload() {
        assertEquals("token" to "abc.def-_123", Captcha.eventOf("captcha:token:abc.def-_123"))
        assertEquals("error" to "超时", Captcha.eventOf("captcha:error:超时"))
        assertEquals("error" to "", Captcha.eventOf("captcha:error"))
        assertEquals("disabled" to "", Captcha.eventOf("  captcha:disabled  "))
        // 不是宿主认识的格式
        assertNull(Captcha.eventOf("安全验证"))
        assertNull(Captcha.eventOf("captcha:"))
        assertNull(Captcha.eventOf(""))
        assertNull(Captcha.eventOf(null))
    }

    @Test
    fun tokenFromEventOnlyAcceptsTokenKind() {
        assertEquals("T", Captcha.tokenFromEvent("captcha:token:T"))
        // payload 允许含冒号（只在第一个冒号切分）
        assertEquals("a:b:c", Captcha.tokenFromEvent("captcha:token:a:b:c"))
        assertNull(Captcha.tokenFromEvent("captcha:error:boom"))
        assertNull(Captcha.tokenFromEvent("captcha:token:"))
        assertNull(Captcha.tokenFromEvent("captcha:token:   "))
        assertNull(Captcha.tokenFromEvent("nope"))
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
        assertTrue(text.contains("Captcha.challengePath("))
        assertTrue(text.contains("Captcha.VERIFY_PATH"))
    }

    @Test
    fun dialogFileWiresTurnstileBridge() {
        val root = sourceRoot() ?: return
        val f = File(root, "ui/CaptchaDialog.kt")
        assertTrue("缺少源文件：ui/CaptchaDialog.kt", f.exists())
        val text = f.readText()
        assertTrue("未注册 JS bridge（AndroidCaptcha）", text.contains("Captcha.JS_BRIDGE_NAME"))
        assertTrue("未使用 Captcha.embedUrl 拼接承载页", text.contains("Captcha.embedUrl("))
        assertTrue("未接 onReceivedTitle 标题兜底回传", text.contains("onReceivedTitle"))
        assertTrue("JS 桥未标注 @JavascriptInterface", text.contains("@JavascriptInterface"))
        assertTrue("未按 provider 分流", text.contains("Captcha.PROVIDER_TURNSTILE"))
        // 旧的滑块-only 文件必须已删除（否则 CaptchaHost 重复定义）
        assertFalse(
            "旧文件仍存在：ui/SliderCaptchaDialog.kt",
            File(root, "ui/SliderCaptchaDialog.kt").exists(),
        )
    }

    @Test
    fun dialogFallsBackToSliderWhenTurnstileFails() {
        val root = sourceRoot() ?: return
        val f = File(root, "ui/CaptchaDialog.kt")
        assertTrue("缺少源文件：ui/CaptchaDialog.kt", f.exists())
        val text = f.readText()
        assertTrue("未定义回退入口 fallbackToSlider", text.contains("fun fallbackToSlider("))
        assertTrue("回退未强制 provider=slider", text.contains("captchaChallenge(provider ="))
        assertTrue("未处理承载页 error 事件", text.contains("\"error\" ->"))
        assertTrue("未处理承载页 loaded 事件", text.contains("\"loaded\" ->"))
        // 滑块渲染必须按实际可用宽度等比缩放（修复窄屏挤压变形）
        assertTrue("滑块舞台未用 BoxWithConstraints 取实际宽度", text.contains("BoxWithConstraints("))
        assertTrue("滑块未按 scale 缩放拼图块", text.contains("challenge.piece.width * scale"))
    }

    @Test
    fun captchaHostIsDeclaredExactlyOnce() {
        val root = sourceRoot() ?: return
        val files = File(root, "ui").listFiles()?.filter { it.extension == "kt" } ?: emptyList()
        val count = files.sumOf { Regex("fun CaptchaHost\\s*\\(").findAll(it.readText()).count() }
        assertEquals("CaptchaHost 应只声明一次", 1, count)
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
