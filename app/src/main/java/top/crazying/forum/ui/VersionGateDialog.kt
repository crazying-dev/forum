package top.crazying.forum.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import kotlin.system.exitProcess
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.core.VersionGate
import top.crazying.forum.theme.ForumTheme

/**
 * 「版本过低」强制更新窗的宿主。
 *
 * 挂在 `ForumRoot` 最外层（先于隐私门判断），由 [App.versionGate] 驱动：
 * 服务端对低于 `min_versions.android` 的请求返回 **HTTP 426 + `VERSION_TOO_LOW`**，
 * 客户端收到后写入该状态，本弹窗随即弹出。
 *
 * 与「发现新版本」不同，这里是**强制**的：
 * * `dismissOnBackPress` / `dismissOnClickOutside` 均为 false，返回键与外部点击都关不掉；
 * * 只有「去更新」（打开下载页后退出应用）与「退出应用」两个出口。
 */
@Composable
fun VersionGateHost() {
    val gate: VersionGate = App.versionGate.value ?: return
    val colors = ForumTheme.colors
    val context = LocalContext.current

    fun quit() {
        context.findHostActivity()?.finishAffinity()
        exitProcess(0)
    }

    AlertDialog(
        // 不可绕过：吞掉返回键与外部点击
        onDismissRequest = { },
        properties = DialogProperties(
            dismissOnBackPress = false,
            dismissOnClickOutside = false,
        ),
        title = {
            Text(
                text = "版本过低",
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = gate.message.ifBlank { "版本过低，请更新" },
                    color = colors.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 20.sp,
                )
                if (gate.minVersion.isNotBlank()) {
                    Text(
                        text = "当前版本 " + Constants.APP_VERSION +
                            "　·　最低要求 " + gate.minVersion,
                        color = colors.textMuted,
                        fontSize = 12.sp,
                    )
                }
                Text(
                    text = "请更新到最新版本后继续使用。",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val url = gate.downloadUrl.ifBlank { Constants.BASE_URL + "/Download" }
                runCatching {
                    context.startActivity(
                        Intent(Intent.ACTION_VIEW, Uri.parse(url))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                }
                quit()
            }) {
                Text("去更新", color = colors.primary)
            }
        },
        dismissButton = {
            TextButton(onClick = { quit() }) {
                Text("退出应用", color = colors.textMuted)
            }
        },
        containerColor = colors.bgCard,
    )
}

/** 从 Compose 的 `LocalContext`（可能是包装过的 Context）向上找到宿主 Activity。 */
private fun Context.findHostActivity(): Activity? {
    var ctx: Context? = this
    while (ctx is ContextWrapper) {
        if (ctx is Activity) return ctx
        ctx = ctx.baseContext
    }
    return null
}
