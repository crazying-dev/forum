package top.crazying.forum.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import kotlin.system.exitProcess
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.screens.PrivacyPolicyPage

/**
 * 首次启动的隐私政策同意门（合规要求）。
 *
 * 行为约定：
 * * 不可绕过：不响应系统返回键 / 点击弹窗外部，也**不预勾选**「同意」；
 * * 必须手动勾选「我已阅读并同意《隐私政策》」后，「同意并继续」才可点击；
 * * 「查看《隐私政策》全文」进入完整政策页，返回后回到本弹窗；
 * * 「不同意」直接退出应用（`finishAffinity` + 结束进程）。
 *
 * 只有 [onAgree] 里把已同意的政策版本写入 `Prefs.privacyAgreedVersion` 后，
 * `ForumRoot` 才会放行进入主界面，并在此时才发起首次联网。
 */
@Composable
fun PrivacyConsentGate(onAgree: () -> Unit) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    var viewingPolicy by remember { mutableStateOf(false) }
    var checked by remember { mutableStateOf(false) }

    // 「查看全文」：整屏渲染隐私政策正文，返回即关闭全文、回到弹窗。
    if (viewingPolicy) {
        PrivacyPolicyPage(onBack = { viewingPolicy = false })
        return
    }

    AlertDialog(
        // 不可绕过：忽略返回键与外部点击
        onDismissRequest = { },
        properties = DialogProperties(
            dismissOnBackPress = false,
            dismissOnClickOutside = false,
        ),
        title = {
            Text(
                text = "隐私政策",
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "「妖精论坛」是《罗小黑战记》的非官方粉丝项目。为了向你提供账号、发帖与互动等功能，" +
                        "我们需要处理你的账号信息、你主动发布的内容与必要的设备信息。我们遵循「最小必要」原则，" +
                        "不会收集你的真实姓名、手机号、精确位置等信息，也不会向任何第三方出售你的信息。",
                    color = colors.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 20.sp,
                )
                Text(
                    text = "点击下方链接可阅读完整政策（当前版本 " +
                        Constants.PRIVACY_POLICY_VERSION + "）。",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                )
                TextButton(
                    onClick = { viewingPolicy = true },
                    contentPadding = PaddingValues(0.dp),
                ) {
                    Text("查看《隐私政策》全文", color = colors.primary, fontSize = 13.sp)
                }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { checked = !checked },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { checked = it },
                        colors = CheckboxDefaults.colors(
                            checkedColor = colors.primary,
                            checkmarkColor = colors.primaryText,
                            uncheckedColor = colors.textMuted,
                        ),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        text = "我已阅读并同意《隐私政策》",
                        color = colors.textSecondary,
                        fontSize = 13.sp,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onAgree, enabled = checked) {
                Text(
                    text = "同意并继续",
                    color = if (checked) colors.primary else colors.textMuted,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = {
                context.findActivity()?.finishAffinity()
                exitProcess(0)
            }) {
                Text("不同意", color = colors.textMuted)
            }
        },
        containerColor = colors.bgCard,
    )
}

/** 从 Compose 的 `LocalContext`（可能是包装过的 Context）向上找到宿主 Activity。 */
private fun Context.findActivity(): Activity? {
    var ctx: Context? = this
    while (ctx is ContextWrapper) {
        if (ctx is Activity) return ctx
        ctx = ctx.baseContext
    }
    return null
}
