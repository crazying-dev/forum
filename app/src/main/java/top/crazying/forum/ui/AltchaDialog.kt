package top.crazying.forum.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.core.AltchaUi
import top.crazying.forum.theme.ForumTheme
import java.util.Locale

/**
 * ALTCHA 求解遮罩宿主（挂在 ForumRoot 最后）。
 *
 * 纯进度层，不拦截业务输入；求解期间用户只能「取消」，取消后本次操作中止。
 */
@Composable
fun AltchaHost() {
    if (!AltchaUi.solving.value) return
    val colors = ForumTheme.colors
    val progress by AltchaUi.progress
    val attempts by AltchaUi.attempts
    val elapsed by AltchaUi.elapsedMs
    val hint by AltchaUi.hint

    BackHandler { AltchaUi.cancel() }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.62f))
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 22.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(colors.bgCard)
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "安全验证",
                color = colors.textPrimary,
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
            )
            CircularProgressIndicator(
                progress = { progress.coerceIn(0f, 1f) },
                color = colors.primary,
                trackColor = colors.bgItemActive,
                strokeWidth = 4.dp,
                modifier = Modifier.height(46.dp),
            )
            Text(
                text = hint,
                color = colors.textSecondary,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
            )
            Text(
                text = "已尝试 ${attempts} 次 · ${String.format(Locale.US, "%.1f", elapsed / 1000.0)}s",
                color = colors.textMuted,
                fontSize = 12.sp,
            )
            Text(
                text = "ALTCHA 工作量证明在本机完成，不会上传你的密码或内容。",
                color = colors.textMuted,
                fontSize = 11.sp,
                lineHeight = 16.sp,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(2.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                TextButton(onClick = { AltchaUi.cancel() }) {
                    Text("取消验证", color = colors.danger)
                }
            }
        }
    }
}
