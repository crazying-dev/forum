package top.crazying.forum.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Captcha
import top.crazying.forum.core.CaptchaPrompt
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme
import kotlin.math.roundToInt

/** 滑动条高度 / 与图片的间距 / 手柄宽度（设计坐标：1 单位 = 1 dp = 1 图像像素）。 */
private const val TRACK_HEIGHT = 40f
private const val TRACK_GAP = 10f
private const val HANDLE_WIDTH = 40f

/** Turnstile 承载页的 WebView 高度（flexible 组件 65px + 提示行 + 留白）。 */
private val EMBED_HEIGHT = 170.dp

/** 一次滑块挑战的本地形态（图像已解码为 Bitmap）。 */
private data class SliderChallenge(
    val token: String,
    val background: Bitmap,
    val piece: Bitmap,
    val pieceY: Int,
    val width: Int,
    val height: Int,
)

/**
 * 人机验证弹窗宿主：挂在 `ForumRoot`，由 [CaptchaPrompt.dialogVisible] 驱动。
 *
 * 任意业务流程调用 `askCaptcha()`（`core/Captcha.kt`）时挂起并置位，
 * 本弹窗把结果回填给挂起的协程：验证通过回 token，取消回 null。
 */
@Composable
fun CaptchaHost() {
    if (!CaptchaPrompt.dialogVisible.value) return
    CaptchaDialog { token -> CaptchaPrompt.complete(token) }
}

/**
 * 人机验证弹窗（统一外壳，按服务端派发的 provider 分流）：
 *
 * * `turnstile` — 用 WebView 加载服务端 `/captcha-embed`，官方组件在网页里渲染，
 *   token 经 JS bridge（`AndroidCaptcha.onEvent`）或 `document.title` 回传；
 * * `slider`  — 自研滑块拼图（拖动手柄 → `POST /api/captcha/verify`）；
 * * `enabled == false` — 服务端已关闭验证，直接以空 token 放行。
 *
 * 注意：Turnstile 的 token 是**一次性**的（官方规定），所以拿到就立即关闭弹窗，
 * 不再走 `/api/captcha/verify` 两步式（服务端在该分支也只做透传）。
 */
@Composable
private fun CaptchaDialog(onFinished: (String?) -> Unit) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    var provider by remember { mutableStateOf(Captcha.PROVIDER_SLIDER) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    /** 中性状态文案（加载中 / 提示拖动 / 请完成验证）。 */
    var hint by remember { mutableStateOf("正在加载验证…") }
    /** 失败文案；与 [hint] 分开存放，避免被下一次加载的提示冲掉。 */
    var error by remember { mutableStateOf("") }
    var challenge by remember { mutableStateOf<SliderChallenge?>(null) }
    var pieceX by remember { mutableStateOf(0f) }
    /** Turnstile 承载页 URL；非空则渲染 WebView。 */
    var embedUrl by remember { mutableStateOf("") }
    /** 每次「换一张 / 刷新」递增，强制重建 WebView（重新加载承载页）。 */
    var embedKey by remember { mutableStateOf(0) }
    /** 只认第一个完成事件（Turnstile 的 callback 可能被重复触发）。 */
    var finished by remember { mutableStateOf(false) }
    /** 已回退过一次自研滑块（避免 Turnstile / 滑块来回抖动）。 */
    var triedFallback by remember { mutableStateOf(false) }
    /** 本次会话只走自研滑块（回退后连「刷新」也不再回到 Turnstile）。 */
    var sliderOnly by remember { mutableStateOf(false) }
    /** 承载页本体是否已加载完成（用于「页面压根没打开」的超时兜底）。 */
    var embedReady by remember { mutableStateOf(false) }

    fun finish(token: String?) {
        if (finished) return
        finished = true
        onFinished(token)
    }

    /**
     * 拉一次挑战（也是「换一张」/ 失败重试入口）。
     *
     * [errorText] 非空时保留上次失败原因；[forceSlider] 为 true 时强制向服务端要自研滑块
     * （Turnstile 出错 / 加载超时后的兜底通道，见 [fallbackToSlider]）。
     */
    fun load(errorText: String = "", forceSlider: Boolean = false) {
        if (forceSlider) sliderOnly = true
        loading = true
        challenge = null
        pieceX = 0f
        embedUrl = ""
        embedReady = false
        error = errorText
        hint = "正在加载验证…"
        val want = if (sliderOnly) Captcha.PROVIDER_SLIDER else ""
        scope.launch {
            val r = App.api.captchaChallenge(provider = want)
            loading = false
            if (!r.ok) {
                error = r.message.ifBlank { "验证加载失败，请点「刷新」重试" }
                hint = ""
                return@launch
            }
            // 服务端未启用人机验证：不弹窗，直接以空 token 放行。
            if (!r.bool("enabled", true)) {
                finish("")
                return@launch
            }
            provider = Captcha.providerOf(r.str("provider").ifBlank { Captcha.PROVIDER_SLIDER })

            if (provider == Captcha.PROVIDER_TURNSTILE) {
                if (r.str("sitekey").trim().isEmpty()) {
                    error = "验证服务未配置，请联系管理员"
                    hint = ""
                    return@launch
                }
                embedUrl = Captcha.embedUrl(
                    baseUrl = Constants.BASE_URL,
                    path = r.str("embed_url").ifBlank { Captcha.EMBED_PATH },
                    theme = if (colors.isDark) "dark" else "light",
                    size = "flexible",
                )
                embedKey += 1
                hint = "请完成下方验证"
                return@launch
            }

            // —— 自研滑块 ——
            val token = r.str("token").trim()
            val bg = decode(r.str("bg"))
            val piece = decode(r.str("piece"))
            if (token.isEmpty() || bg == null || piece == null) {
                error = "验证图像解析失败，请点「刷新」重试"
                hint = ""
                return@launch
            }
            val w = if (r.int("width", 0) > 0) r.int("width") else bg.width
            val h = if (r.int("height", 0) > 0) r.int("height") else bg.height
            challenge = SliderChallenge(
                token = token,
                background = bg,
                piece = piece,
                pieceY = r.int("y", 0),
                width = w,
                height = h,
            )
            hint = "拖动滑块，把拼图块移到缺口处"
        }
    }

    /**
     * Turnstile 出错 / 超时 → 自动回退自研滑块（只回退一次，避免来回抖动）。
     *
     * 服务端 `POST /api/captcha/challenge?provider=slider` 会强制下发拼图挑战，
     * 即便全局 provider 仍是 turnstile；回退后 [sliderOnly] 置位，「刷新」也不再回到 Turnstile。
     */
    fun fallbackToSlider(): Boolean {
        if (triedFallback) return false
        triedFallback = true
        load(forceSlider = true)
        return true
    }

    /** 松手后提交坐标；通过则回传 token，否则保留错误文案并换一张重来。 */
    fun verify() {
        val c = challenge ?: return
        if (busy || loading) return
        busy = true
        hint = "正在验证…"
        scope.launch {
            val r = App.api.captchaVerify(c.token, pieceX.roundToInt())
            busy = false
            if (r.ok) {
                finish(c.token)
            } else {
                // 失败原因作为参数交给 load 保留，不会再被「正在加载…」冲掉。
                load(r.message.ifBlank { "验证未通过，请重试" })
            }
        }
    }

    /** 承载页回传的事件（JS bridge 或 document.title）。 */
    fun onEmbedEvent(kind: String, payload: String) {
        when (kind) {
            "token" -> {
                val t = payload.trim()
                if (t.isNotEmpty()) finish(t)
            }
            "loaded" -> embedReady = true
            "error" -> {
                // Turnstile 组件报错 / 加载失败 / WebView 打不开承载页 → 回退自研滑块。
                if (fallbackToSlider()) return
                error = when (payload.trim()) {
                    "disabled" -> "人机验证已关闭"
                    "unconfigured" -> "验证服务未配置，请联系管理员"
                    else -> payload.ifBlank { "人机验证失败，请重试" }
                }
                hint = ""
                busy = false
            }
            else -> Unit
        }
    }

    LaunchedEffect(Unit) { load() }

    // Turnstile 承载页「压根没打开」的兜底：WebView 静默失败时页面不会回报错事件。
    // 仅在页面尚未 load 完成时回退，避免打扰正在点击验证的用户。
    LaunchedEffect(provider, embedUrl, embedKey) {
        if (provider == Captcha.PROVIDER_TURNSTILE && embedUrl.isNotEmpty() && !embedReady) {
            delay(12000)
            if (!finished && !embedReady) fallbackToSlider()
        }
    }

    val retryLabel = if (provider == Captcha.PROVIDER_TURNSTILE) "刷新" else "换一张"

    AlertDialog(
        onDismissRequest = { if (!busy) finish(null) },
        title = {
            Text("安全验证", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = if (provider == Captcha.PROVIDER_TURNSTILE) {
                        "为了确认你不是机器人，请完成下方验证。"
                    } else {
                        "为了确认你不是机器人，请拖动滑块把拼图块移到缺口位置。"
                    },
                    color = colors.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                )

                if (provider == Captcha.PROVIDER_TURNSTILE && embedUrl.isNotEmpty()) {
                    TurnstileEmbed(
                        url = embedUrl,
                        reloadKey = embedKey,
                        onEvent = { k, p -> onEmbedEvent(k, p) },
                    )
                } else {
                    val c = challenge
                    if (c != null) {
                        SliderStageView(
                            challenge = c,
                            pieceX = pieceX,
                            enabled = !busy,
                            onPieceX = { pieceX = it },
                            onRelease = { verify() },
                        )
                    } else {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(150.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(colors.bgInput),
                            contentAlignment = Alignment.Center,
                        ) {
                            if (loading) {
                                CircularProgressIndicator(color = colors.primary, strokeWidth = 3.dp)
                            } else {
                                Text(
                                    text = error.ifBlank { "请点「刷新」重试" },
                                    color = colors.danger,
                                    fontSize = 12.sp,
                                    textAlign = TextAlign.Center,
                                    modifier = Modifier.padding(horizontal = 16.dp),
                                )
                            }
                        }
                    }
                }

                if (hint.isNotEmpty()) {
                    Text(hint, color = colors.textMuted, fontSize = 12.sp)
                }
                if (error.isNotEmpty() && challenge != null) {
                    Text(error, color = colors.danger, fontSize = 12.sp)
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = { finish(null) }) {
                Text("取消", color = colors.textMuted)
            }
        },
        dismissButton = {
            TextButton(enabled = !busy && !loading, onClick = { load() }) {
                Text(retryLabel, color = colors.primary)
            }
        },
        containerColor = colors.bgCard,
    )
}

/** data URL → Bitmap；失败返回 null。 */
private fun decode(dataUrl: String): Bitmap? {
    val bytes = Captcha.decodeDataUrl(dataUrl) ?: return null
    return runCatching { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }.getOrNull()
}

// ──────────────────────────────────────────────
// Turnstile：WebView 承载 + JS bridge / 标题回传
// ──────────────────────────────────────────────

/**
 * `@JavascriptInterface` 回调跑在 WebView 的 JavaBridge 线程上，
 * 必须 post 回主线程再改 Compose 状态。；[events] 用 [rememberUpdatedState] 包住，
 * 这样 WebView 只创建一次也不会拿到过期的闭包。
 */
private class CaptchaBridge(
    private val main: Handler,
    private val events: State<(String, String) -> Unit>,
) {
    @JavascriptInterface
    fun onEvent(kind: String?, payload: String?) {
        val k = (kind ?: "").trim().lowercase()
        if (k.isEmpty()) return
        val p = payload ?: ""
        main.post { events.value(k, p) }
    }
}

/**
 * 把一个 URL 加载进 WebView。
 *
 * [url] / [reloadKey] 变化时会重建 WebView（旧实例在 [DisposableEffect] 里 destroy）。
 * 导航限制在站内与 Cloudflare 验证域内，避免用户点外链离开验证页。
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun TurnstileEmbed(
    url: String,
    reloadKey: Int,
    onEvent: (String, String) -> Unit,
) {
    val context = LocalContext.current
    val events = rememberUpdatedState(onEvent)
    val main = remember { Handler(Looper.getMainLooper()) }

    // AndroidView 的 factory 只在节点首次创建时执行，所以"重新加载"必须换 key，
    // 让整个节点（连同 WebView）重建；旧实例在 DisposableEffect 里 destroy。
    key(url, reloadKey) {
        val view = remember {
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.loadWithOverviewMode = false
                settings.useWideViewPort = false
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.javaScriptCanOpenWindowsAutomatically = true
                settings.setSupportMultipleWindows(false)
                CookieManager.getInstance().setAcceptCookie(true)
                CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

                addJavascriptInterface(CaptchaBridge(main, events), Captcha.JS_BRIDGE_NAME)

                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(
                        wv: WebView?,
                        request: WebResourceRequest?,
                    ): Boolean {
                        val target = request?.url?.toString().orEmpty()
                        // 站内承载页 / Cloudflare 验证域 / about:blank 放行，其余外链一律拦下。
                        return !(target.startsWith(Constants.BASE_URL) ||
                            target.contains("challenges.cloudflare.com") ||
                            target.startsWith("about:"))
                    }

                    override fun onPageFinished(wv: WebView?, url: String?) {
                        // 承载页本体已加载（组件是否就绪另由页面回报）→ 关闭宿主加载超时。
                        events.value("loaded", "")
                    }

                    override fun onReceivedError(
                        wv: WebView?,
                        request: WebResourceRequest?,
                        error: WebResourceError?,
                    ) {
                        // 只有主文档失败才算「页打不开」；Cloudflare 子资源失败由页面自行回报。
                        if (request?.isForMainFrame == true) events.value("error", "load")
                    }
                }

                webChromeClient = object : WebChromeClient() {
                    override fun onReceivedTitle(wv: WebView?, title: String?) {
                        val e = Captcha.eventOf(title) ?: return
                        // WebChromeClient 回调已在主线程。
                        events.value(e.first, e.second)
                    }
                }

                loadUrl(url)
            }
        }

        DisposableEffect(view) {
            onDispose { runCatching { view.destroy() } }
        }

        AndroidView(
            factory = { view },
            modifier = Modifier
                .fillMaxWidth()
                .height(EMBED_HEIGHT)
                .clip(RoundedCornerShape(8.dp))
                .background(ForumTheme.colors.bgInput),
        )
    }
}

/**
 * 拼图舞台：上方是背景图 + 可拖动的拼图块，下方是滑动条。
 *
 * 渲染宽度 = min(图片宽, 可用宽度)：窄屏（弹窗容器可能不足 320dp）按比例等比缩放，
 * 背景与拼图块不会“挤压变形”（旧实现用固定 320dp 宽 + FillBounds，窄屏下会拉扁）。
 * 滑块行程（travel）也按**实际渲染宽度**计算，因此上报的 `captcha_x` 与画面、与服务端
 * 容差判定始终同尺——修复“图片变形 + 验证永远失败”。
 *
 * `captcha_x` 坐标系仍是服务端**图像像素**（`0..maxPieceX`，与 `Captcha.pieceXFromDrag` 同口径）。
 */
@Composable
private fun SliderStageView(
    challenge: SliderChallenge,
    pieceX: Float,
    enabled: Boolean,
    onPieceX: (Float) -> Unit,
    onRelease: () -> Unit,
) {
    val colors = ForumTheme.colors
    val density = LocalDensity.current.density

    val stageW = challenge.width.toFloat()
    val stageH = challenge.height.toFloat()

    // pointerInput 会长期持有首次创建的 lambda，回调必须取「最新」的那份。
    val onPieceXNow by rememberUpdatedState(onPieceX)
    val onReleaseNow by rememberUpdatedState(onRelease)

    // 手柄已滑过的距离（与 travel 同单位，仅作为拖拽量累计）。
    var dragDp by remember { mutableStateOf(0f) }

    BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
        val availW = maxWidth.value
        val renderW = (if (stageW > 0f && availW > 0f) minOf(stageW, availW) else maxOf(stageW, 1f))
            .coerceAtLeast(1f)
        val scale = if (stageW > 0f) renderW / stageW else 1f
        val renderH = stageH * scale
        // 行程与缩放都基于**实际渲染宽度**，拖动距离才与画面一致。
        val travel = (renderW - HANDLE_WIDTH).coerceAtLeast(1f)
        val maxPieceX = (stageW - challenge.piece.width).coerceAtLeast(1f)
        val handleX = Captcha.handleXFromPiece(pieceX, travel, maxPieceX)

        Column(
            modifier = Modifier.width(renderW.dp),
            verticalArrangement = Arrangement.spacedBy(TRACK_GAP.dp),
        ) {
            // ── 背景 + 拼图块 ──
            Box(
                modifier = Modifier
                    .width(renderW.dp)
                    .height(renderH.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(colors.bgInput),
            ) {
                Image(
                    bitmap = challenge.background.asImageBitmap(),
                    contentDescription = null,
                    contentScale = ContentScale.FillBounds,
                    modifier = Modifier.fillMaxSize(),
                )
                Image(
                    bitmap = challenge.piece.asImageBitmap(),
                    contentDescription = null,
                    contentScale = ContentScale.FillBounds,
                    modifier = Modifier
                        .offset(x = (pieceX * scale).dp, y = (challenge.pieceY * scale).dp)
                        .size((challenge.piece.width * scale).dp, (challenge.piece.height * scale).dp),
                )
            }

            // ── 滑动条 ──
            Box(
                modifier = Modifier
                    .width(renderW.dp)
                    .height(TRACK_HEIGHT.dp)
                    .clip(RoundedCornerShape(TRACK_HEIGHT / 2f))
                    .background(colors.bgInput)
                    .border(1.dp, colors.border, RoundedCornerShape(TRACK_HEIGHT / 2f))
                    .pointerInput(enabled, travel, maxPieceX, density) {
                        if (!enabled) return@pointerInput
                        detectDragGestures(
                            onDragStart = { },
                            onDrag = { change, amount ->
                                change.consume()
                                val next = (dragDp + amount.x / density).coerceIn(0f, travel)
                                dragDp = next
                                onPieceXNow(Captcha.pieceXFromDrag(next, travel, maxPieceX))
                            },
                            onDragEnd = { onReleaseNow() },
                            onDragCancel = { },
                        )
                    },
            ) {
                // 已滑过区域
                Box(
                    modifier = Modifier
                        .fillMaxHeight()
                        .width((handleX + HANDLE_WIDTH / 2f).dp)
                        .background(colors.primary.copy(alpha = 0.22f)),
                )
                // 手柄
                Box(
                    modifier = Modifier
                        .offset(x = handleX.dp)
                        .width(HANDLE_WIDTH.dp)
                        .height(TRACK_HEIGHT.dp)
                        .clip(RoundedCornerShape(TRACK_HEIGHT / 2f))
                        .background(if (enabled) colors.primary else colors.bgItemActive),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "》",
                        color = colors.primaryText,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}
