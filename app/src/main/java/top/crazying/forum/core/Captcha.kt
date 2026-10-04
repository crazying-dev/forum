package top.crazying.forum.core

import android.util.Base64
import androidx.compose.runtime.mutableStateOf
import kotlinx.coroutines.CompletableDeferred
import org.json.JSONObject

/**
 * 滑块拼图人机验证（CAPTCHA）的客户端支持。
 *
 * 与服务端 `forum/api/captcha/__init__.py` 同源：
 * * `POST /api/captcha/challenge` → `{success, token, bg, piece, y, width, height, piece_size}`
 *   （`bg` / `piece` 是 `data:image/png;base64,...` 的 data URL；服务端未启用时返回
 *   `{success: true, enabled: false, token: ""}`，客户端应直接跳过弹窗）；
 * * `POST /api/captcha/verify` → 提交滑块位置，通过后返回原 token 并置 `solved`；
 * * 受保护接口在缺少有效 token 时返回 **HTTP 400 + `code=CAPTCHA_REQUIRED`**。
 *
 * 本文件只放**纯逻辑**（错误码 / 端点表 / data URL 解析 / 拖拽坐标映射），
 * 全部可在 JVM 单测里直接跑，不依赖 Android 运行时；
 * 弹窗与图像解码见 `ui/SliderCaptchaDialog.kt`。
 */
object Captcha {

    /** 服务端在缺少 / 失效人机验证时返回的错误码（HTTP 400）。 */
    const val REQUIRED_CODE = "CAPTCHA_REQUIRED"

    /** 请求体字段名（与服务端同源）。 */
    const val FIELD_TOKEN = "captcha_token"
    const val FIELD_X = "captcha_x"

    /** 申请一次滑块挑战。 */
    const val CHALLENGE_PATH = "/api/captcha/challenge"

    /** 提交滑块位置换取通过状态。 */
    const val VERIFY_PATH = "/api/captcha/verify"

    // ────────────────── provider（服务端下发） ──────────────────
    /** 自研滑块拼图（兜底）。 */
    const val PROVIDER_SLIDER = "slider"

    /** Cloudflare Turnstile（由 WebView 内嵌官方组件）。 */
    const val PROVIDER_TURNSTILE = "turnstile"

    /** 服务端已关闭人机验证，客户端直接放行。 */
    const val PROVIDER_OFF = "off"

    /**
     * WebView 内嵌承载页，路径与 `forum/api/captcha/__init__.py` 的
     * `CAPTCHA_EMBED_PATH` 同源。
     */
    const val EMBED_PATH = "/captcha-embed"

    /** 承载页与宿主之间的消息前缀：`captcha:<kind>:<payload>`。 */
    const val EVENT_PREFIX = "captcha:"

    /** JS bridge 的名字（承载页里 `window.AndroidCaptcha.onEvent`）。 */
    const val JS_BRIDGE_NAME = "AndroidCaptcha"

    /**
     * 需要携带人机验证 token 的接口路径。
     *
     * 与 Windows 端 `app/api.py` 的 `CAPTCHA_PROTECTED_ENDPOINTS` 同口径；
     * 刻意**不含** `/api/user/password`（改密终步）与 `/api/user/email`（换绑终步）——
     * 服务端只保护它们的「发送验证码」前置步骤。
     */
    val PROTECTED_ENDPOINTS: List<String> = listOf(
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

    /** 是否命中「需要人机验证」（服务端固定 400 + [REQUIRED_CODE]）。纯函数。 */
    fun isRequired(code: String?): Boolean = (code ?: "").trim() == REQUIRED_CODE

    /** 取 data URL 的载荷（`data:image/png;base64,AAAA` → `AAAA`）。纯函数。 */
    fun dataUrlPayload(dataUrl: String): String {
        val s = (dataUrl ?: "").trim()
        if (s.isEmpty()) return ""
        val comma = s.indexOf(',')
        return if (comma < 0) s else s.substring(comma + 1).trim()
    }

    /** data URL → 图片字节；解码失败 / 内容为空返回 null。 */
    fun decodeDataUrl(dataUrl: String): ByteArray? {
        val payload = dataUrlPayload(dataUrl)
        if (payload.isEmpty()) return null
        val bytes = runCatching { Base64.decode(payload, Base64.DEFAULT) }.getOrNull() ?: return null
        return if (bytes.isEmpty()) null else bytes
    }

    /**
     * 把 token 合进请求体（**不改动入参**）。
     *
     * token 为空时原样返回：服务端未启用人机验证、或该流程本就不需要验证时，
     * 请求体里不该多出这个字段（Windows / Web 同样是「有才带」）。
     */
    fun withToken(body: JSONObject, token: String): JSONObject {
        if (token.isBlank()) return body
        return JSONObject(body.toString()).put(FIELD_TOKEN, token)
    }

    /**
     * 拖拽位移 → 拼图块左上角 x（设计坐标：1 单位 = 1 dp = 1 图像像素）。
     *
     * @param dragDx    手柄已经滑过的距离（与 [travel] 同单位）
     * @param travel    手柄可滑动的总距离
     * @param maxPieceX 拼图块可到达的最大 x（= 舞台宽 − 拼图块宽）
     */
    fun pieceXFromDrag(dragDx: Float, travel: Float, maxPieceX: Float): Float {
        if (travel <= 0f || maxPieceX <= 0f) return 0f
        return (dragDx / travel * maxPieceX).coerceIn(0f, maxPieceX)
    }

    /** 拼图块 x → 手柄左上角 x（仅用于绘制）。与 [pieceXFromDrag] 互逆。 */
    fun handleXFromPiece(pieceX: Float, travel: Float, maxPieceX: Float): Float {
        if (maxPieceX <= 0f || travel <= 0f) return 0f
        return (pieceX / maxPieceX * travel).coerceIn(0f, travel)
    }

    /**
     * 强制指定 provider 的挑战路径（客户端回退时用 `"slider"`）。
     *
     * `provider` 为空时返回原始 [CHALLENGE_PATH]；否则拼上 `?provider=<归一化值>`。
     * 与服务端 `api/captcha/api_captcha_challenge()` 的 `request.args.get("provider")` 同源。纯函数。
     */
    fun challengePath(provider: String? = ""): String {
        val p = (provider ?: "").trim().lowercase()
        return if (p.isEmpty()) CHALLENGE_PATH else CHALLENGE_PATH + "?provider=" + p
    }

    /**
     * 归一化服务端下发的 provider；未知 / 空值一律回退 [PROVIDER_SLIDER]。
     *
     * 与服务端 `api/captcha/_provider()` 同口径（那边缺密钥时也会回退 slider），
     * 双端都不信任对方一定给对值。纯函数。
     */
    fun providerOf(raw: String?): String =
        when ((raw ?: "").trim().lowercase()) {
            PROVIDER_TURNSTILE -> PROVIDER_TURNSTILE
            PROVIDER_OFF, "none", "disable", "disabled", "0", "false" -> PROVIDER_OFF
            else -> PROVIDER_SLIDER
        }

    /**
     * 拼接 WebView 承载页 URL。
     *
     * @param baseUrl 站点根（[Constants.BASE_URL]）
     * @param path    服务端下发的 `embed_url`（相对路径或完整 URL）
     * @param theme   `dark` / `light`，其他值按 `light` 处理
     * @param size    `normal` / `flexible` / `compact`，默认 flexible（弹窗容器窄）
     */
    fun embedUrl(
        baseUrl: String,
        path: String? = EMBED_PATH,
        theme: String? = null,
        size: String? = null,
    ): String {
        val root = (baseUrl ?: "").trim().trimEnd('/')
        val p = (path ?: "").trim().ifBlank { EMBED_PATH }
        val abs = when {
            p.startsWith("http://") || p.startsWith("https://") -> p
            p.startsWith("//") -> "https:$p"
            p.startsWith("/") -> root + p
            else -> "$root/$p"
        }
        val t = if ((theme ?: "").trim().lowercase() == "dark") "dark" else "light"
        val s = when ((size ?: "").trim().lowercase()) {
            "normal" -> "normal"
            "compact" -> "compact"
            else -> "flexible"
        }
        val sep = if (abs.contains('?')) '&' else '?'
        return "$abs${sep}theme=$t&lang=zh-cn&size=$s"
    }

    /**
     * 解析承载页回传的事件 `captcha:<kind>:<payload>`。
     *
     * 不是该格式（宿主不认识）返回 null。payload 允许含 `:`（只在第一个冒号切分）。
     * 纯函数，便于 JVM 单测。
     */
    fun eventOf(raw: String?): Pair<String, String>? {
        val s = (raw ?: "").trim()
        if (!s.startsWith(EVENT_PREFIX)) return null
        val rest = s.substring(EVENT_PREFIX.length)
        val i = rest.indexOf(':')
        val kind = (if (i < 0) rest else rest.substring(0, i)).trim().lowercase()
        val payload = if (i < 0) "" else rest.substring(i + 1)
        if (kind.isEmpty()) return null
        return kind to payload
    }

    /** 取 `captcha:token:<TOKEN>` 里的 token；其他事件 / 空 token 返回 null。纯函数。 */
    fun tokenFromEvent(raw: String?): String? {
        val (kind, payload) = eventOf(raw) ?: return null
        if (kind != "token") return null
        val t = payload.trim()
        return if (t.isEmpty()) null else t
    }
}

/**
 * 「需要人机验证」时的挂起桥：业务程调用 [ask] 后挂起，弹窗完成后 [complete] 唤醒。
 *
 * 挂在 `ForumRoot` 的 `CaptchaHost()` 监听 [dialogVisible]；
 * 同一时刻只允许一个验证请求（并发调用直接返回 null，避免弹窗叠成一摞）。
 *
 * 线程约定：只应在主线程调用（Compose 的 `rememberCoroutineScope` 默认即主线程）。
 */
object CaptchaPrompt {

    /** Compose 可观察：当前是否有待处理的验证请求。 */
    val dialogVisible = mutableStateOf(false)

    private var deferred: CompletableDeferred<String?>? = null

    /**
     * 弹出验证窗并挂起当前协程。
     *
     * @return 验证通过后返回 token（服务端未启用时为空串）；用户取消 / 并发冲突返回 null。
     */
    suspend fun ask(): String? {
        if (deferred != null) return null
        val d = CompletableDeferred<String?>()
        deferred = d
        dialogVisible.value = true
        return try {
            d.await()
        } finally {
            dialogVisible.value = false
            deferred = null
        }
    }

    /** 弹窗侧回调；[token] 为 null 表示用户取消。 */
    fun complete(token: String?) {
        val d = deferred ?: return
        if (!d.isCompleted) d.complete(token)
    }
}

/**
 * 顶层便捷入口：拿到 token 再继续业务；返回 null 表示用户取消，调用方应直接中断当前流程。
 *
 * 语义与 Windows 端 `ask_captcha()` 对齐。
 */
suspend fun askCaptcha(): String? = CaptchaPrompt.ask()
