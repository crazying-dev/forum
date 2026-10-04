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
