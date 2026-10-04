package top.crazying.forum.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Captcha
import top.crazying.forum.core.CaptchaPrompt
import top.crazying.forum.theme.ForumTheme
import kotlin.math.roundToInt
/** 滑动条高度 / 与图片的间距 / 手柄宽度（设计坐标：1 单位 = 1 dp = 1 图像像素）。 */
private const val TRACK_HEIGHT = 40f
private const val TRACK_GAP = 10f
private const val HANDLE_WIDTH = 40f

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
 * 滑块验证弹窗宿主：挂在 `ForumRoot`，由 [CaptchaPrompt.dialogVisible] 驱动。
 *
 * 任意业务流程调用 `askCaptcha()`（`core/Captcha.kt`）时挂起并置位，
 * 本弹窗把结果回填给挂起的协程：验证通过回 token，取消回 null。
 */
@Composable
fun CaptchaHost() {
    if (!CaptchaPrompt.dialogVisible.value) return
    SliderCaptchaDialog { token -> CaptchaPrompt.complete(token) }
}

/**
 * 滑块拼图弹窗。
 *
 * 与服务端 `POST /api/captcha/challenge` / `verify` 交互：
 * 1. 打开时拉一张挑战图（`bg` + `piece` 两张 data URL PNG）；
 * 2. 用户拖动手柄，拼图块随之右移；松手时提交 `captcha_x`（图像像素坐标）；
 * 3. 通过则带着 token 关闭弹窗，未通过则自动换一张重来。
 *
 * 服务端未启用人机验证时（`enabled == false`）直接以空串完成，不打扰用户。
 */
@Composable
private fun SliderCaptchaDialog(onFinished: (String?) -> Unit) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("正在加载验证图像…") }
    var challenge by remember { mutableStateOf<SliderChallenge?>(null) }
    var pieceX by remember { mutableStateOf(0f) }

    // 拉一张新的挑战图（也是「换一张」/ 验证失败后的重试入口）。
    fun load() {
        loading = true
        challenge = null
        pieceX = 0f
        status = "正在加载验证图像…"
        scope.launch {
            val r = App.api.captchaChallenge()
            loading = false
            if (!r.ok) {
                status = r.message.ifBlank { "验证图像加载失败，请点「换一张」重试" }
                return@launch
            }
            // 服务端未启用人机验证：不弹窗，直接以空 token 放行。
            if (!r.bool("enabled", true)) {
                onFinished("")
                return@launch
            }
            val token = r.str("token").trim()
            val bg = decode(r.str("bg"))
            val piece = decode(r.str("piece"))
            if (token.isEmpty() || bg == null || piece == null) {
                status = "验证图像解析失败，请点「换一张」重试"
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
            status = "拖动滑块，把拼图块移到缺口处"
        }
    }

    // 松手后提交坐标；通过则回传 token，否则换一张重来。
    fun verify() {
        val c = challenge ?: return
        if (busy || loading) return
        busy = true
        status = "正在验证…"
        scope.launch {
            val r = App.api.captchaVerify(c.token, pieceX.roundToInt())
            busy = false
            if (r.ok) {
                onFinished(c.token)
            } else {
                status = r.message.ifBlank { "验证未通过，请重试" }
                load()
            }
        }
    }

    LaunchedEffect(Unit) { load() }

    AlertDialog(
        onDismissRequest = { if (!busy) onFinished(null) },
        title = {
            Text("安全验证", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "为了确认你不是机器人，请拖动滑块把拼图块移到缺口位置。",
                    color = colors.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                )
                val c = challenge
                if (c != null) {
                    SliderStageView(
                        challenge = c,
                        pieceX = pieceX,
                        enabled = !busy,
                        onPieceX = { pieceX = it },
                        onRelease = { verify() },
                    )
                    Text(status, color = colors.textMuted, fontSize = 12.sp)
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
                                text = status,
                                color = colors.danger,
                                fontSize = 12.sp,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.padding(horizontal = 16.dp),
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = { onFinished(null) }) {
                Text("取消", color = colors.textMuted)
            }
        },
        dismissButton = {
            TextButton(enabled = !busy && !loading, onClick = { load() }) {
                Text("换一张", color = colors.primary)
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

/**
 * 拼图舞台：上方是背景图 + 可拖动的拼图块，下方是滑动条。
 *
 * 坐标体系：背景图 1 像素 = 1 dp，因此 320×180 的图渲染为 320×180 dp
 * （绝大多数手机宽屏都在 360 dp 以上，不会溢出）；拖拽位移换算成
 * 「图像像素」坐标后直接作为 `captcha_x` 上报，与服务端的容差判定同尺。
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
    val travel = (stageW - HANDLE_WIDTH).coerceAtLeast(1f)
    val maxPieceX = (stageW - challenge.piece.width).coerceAtLeast(1f)

    // pointerInput 会长期持有首次创建的 lambda，回调必须取「最新」的那份。
    val onPieceXNow by rememberUpdatedState(onPieceX)
    val onReleaseNow by rememberUpdatedState(onRelease)

    // 手柄已滑过的距离（与 travel 同单位，仅作为拖拽量累计）。
    var dragDp by remember { mutableStateOf(0f) }

    val handleX = Captcha.handleXFromPiece(pieceX, travel, maxPieceX)

    Column(
        modifier = Modifier.width(stageW.dp),
        verticalArrangement = Arrangement.spacedBy(TRACK_GAP.dp),
    ) {
        // ── 背景 + 拼图块 ──
        Box(
            modifier = Modifier
                .width(stageW.dp)
                .height(stageH.dp)
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
                    .offset(x = pieceX.dp, y = challenge.pieceY.toFloat().dp)
                    .size(challenge.piece.width.dp, challenge.piece.height.dp),
            )
        }

        // ── 滑动条 ──
        Box(
            modifier = Modifier
                .width(stageW.dp)
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
