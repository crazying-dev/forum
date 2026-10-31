package top.crazying.forum.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.core.App
import top.crazying.forum.theme.ForumTheme

/**
 * 进程内「已关闭」标记。
 *
 * 用文件级变量而不是 rememberSaveable：Activity 重建（旋转屏幕）不重弹，
 * 而进程真正被回收后再次启动（冷启动）会重新弹——与「每次冷启动弹一次」的口径一致。
 */
private var dismissedInProcess = false

/**
 * 启动公告：论坛本体已升级到 ov2，而本 APP 功能落后、问题较多，正在计划开发 ov2 APP。
 *
 * 显示口径：**每次冷启动弹一次**（进程内只弹一次），
 * 点「我知道了」/ 点外部 / 返回键均可关闭，不阻塞使用。
 */
@Composable
fun Ov2NoticeHost() {
    var visible by remember { mutableStateOf(!dismissedInProcess) }
    // 强制版本门、「发现新版本」优先级更高：它们存在时公告先让位，关掉后再出现。
    val hasPriorityDialog = App.versionGate.value != null || App.updateInfo.value != null
    if (!visible || hasPriorityDialog) return
    val colors = ForumTheme.colors

    fun dismiss() {
        dismissedInProcess = true
        visible = false
    }

    AlertDialog(
        onDismissRequest = { dismiss() },
        title = {
            Text(
                text = "关于本版本 APP 的说明",
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "考虑到论坛本体已经升级为新的 ov2 版本，而 APP 功能落后，且一堆问题，" +
                        "所以，正在计划开发 ov2 版本的 APP。",
                    color = colors.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 21.sp,
                )
                Text(
                    text = "注：此版本的 APP 依然会收到必要的升级推送，直至 ov2 APP 完成为止。",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                    lineHeight = 20.sp,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { dismiss() }) {
                Text("我知道了", color = colors.primary)
            }
        },
        containerColor = colors.bgCard,
    )
}
