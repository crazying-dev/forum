package top.crazying.forum.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.core.AltchaUi
import top.crazying.forum.core.Phase
import top.crazying.forum.theme.ForumColors
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.PrimaryButton

/**
 * ALTCHA 等待/失败弹窗宿主（挂在 ForumRoot 最后）。
 *
 * 极简卡片：求解中只给不确定转圈 + 取消；失败时同卡片内切换原因与「重试 / 取消」。
 * 遮罩层消费点击，避免穿透到页面；按钮是上层子节点，仍可正常点击。
 */
@Composable
fun AltchaHost() {
    val phase by AltchaUi.phase
    if (phase == Phase.Idle) return
    val colors = ForumTheme.colors
    val failure by AltchaUi.failureMessage

    BackHandler { AltchaUi.cancel() }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.62f))
            .pointerInput(Unit) { detectTapGestures { } }
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        BoxWithConstraints(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            val cardWidth = minOf(maxWidth * 0.8f, 300.dp)
            Column(
                modifier = Modifier
                    .width(cardWidth)
                    .clip(RoundedCornerShape(18.dp))
                    .background(colors.bgCard)
                    .padding(22.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                when (phase) {
                    Phase.Solving -> SolvingContent(colors)
                    Phase.Failed -> FailedContent(colors, failure)
                    Phase.Idle -> Unit
                }
            }
        }
    }
}

@Composable
private fun SolvingContent(colors: ForumColors) {
        CircularProgressIndicator(
            color = colors.primary,
            // 浅色主题的 bgItemActive 偏白，改用品牌色低透明度，避免近白环。
            trackColor = colors.primary.copy(alpha = 0.15f),
            strokeWidth = 4.dp,
            modifier = Modifier.size(44.dp),
        )
    Text(
        text = "正在验证…",
        color = colors.textPrimary,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
    )
    Text(
        text = "请稍候，马上就好",
        color = colors.textMuted,
        fontSize = 12.5.sp,
        textAlign = TextAlign.Center,
    )
    TextButton(onClick = { AltchaUi.cancel() }) {
        Text("取消验证", color = colors.textMuted, fontSize = 13.sp)
    }
}

@Composable
private fun FailedContent(colors: ForumColors, message: String) {
    Box(
        modifier = Modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(colors.danger.copy(alpha = 0.14f))
            .clearAndSetSemantics { },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "!",
            color = colors.danger,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
        )
    }
    Text(
        text = "验证失败",
        color = colors.textPrimary,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
    )
    Text(
        text = message,
        color = colors.textMuted,
        fontSize = 12.5.sp,
        textAlign = TextAlign.Center,
    )
    PrimaryButton(
        text = "重试",
        onClick = { AltchaUi.retry() },
        modifier = Modifier.fillMaxWidth(),
    )
    TextButton(onClick = { AltchaUi.cancel() }) {
        Text("取消", color = colors.textMuted, fontSize = 13.sp)
    }
}
