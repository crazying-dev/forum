package top.crazying.forum.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.UpdateInfo
import top.crazying.forum.core.Updater
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.toast
import java.io.File

/**
 * 「发现新版本」对话框的宿主。
 *
 * 挂在 `ForumRoot` 里，由 [App.updateInfo] 驱动：
 * 冷启动自动检查（见 `Updater.autoCheck`）或设置页手动检查发现新版本时，
 * 该状态被写入，对话框自动弹出。
 *
 * 点击「立即更新」后的完整链路：
 * 1. 先查「安装未知应用」权限：没授权就跳系统授权页，回来再点一次；
 * 2. 按回退链下载到 `cacheDir/updates/` 并校验体积 + sha256；
 * 3. 成功后经 FileProvider 调起系统安装器（Android 不允许应用静默自装）。
 */
@Composable
fun UpdateDialogHost() {
    val info: UpdateInfo? = App.updateInfo.value
    val current = info ?: return
    UpdateDialog(current) {
        // 「以后再说」：记住版本号，24 小时内的自动检查不再为它打扰
        App.prefs.updateSkipVersion = current.latest
        App.updateInfo.value = null
    }
}

@Composable
private fun UpdateDialog(info: UpdateInfo, onDismiss: () -> Unit) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val release = info.release

    // 同一版本重新打开时重置；换版本时 also 重置
    var busy by remember(info.latest) { mutableStateOf(false) }
    var progress by remember(info.latest) { mutableStateOf(-1f) }
    var line by remember(info.latest) { mutableStateOf("") }
    var error by remember(info.latest) { mutableStateOf<String?>(null) }
    var ready by remember(info.latest) { mutableStateOf<File?>(null) }

    fun requestInstallPermission() {
        try {
            context.startActivity(Updater.installPermissionIntent(context))
            toast(context, "请先允许「安装未知应用」，再回来点「立即更新」")
        } catch (e: Exception) {
            error = "无法打开授权页面，请在系统设置里手动允许本应用的「安装未知应用」"
        }
    }

    fun launchInstall(file: File) {
        if (!Updater.canInstall(context)) {
            requestInstallPermission()
            return
        }
        try {
            Updater.installApk(context, file)
        } catch (e: Exception) {
            error = "拉起安装器失败：" + (e.message ?: "未知错误")
        }
    }

    fun beginDownload(target: top.crazying.forum.core.UpdateRelease) {
        if (busy) return
        busy = true
        error = null
        line = ""
        progress = 0f
        scope.launch {
            try {
                val file = Updater.download(context, target) { done, total, label ->
                    line = label
                    progress = if (total > 0L) {
                        (done.toFloat() / total).coerceIn(0f, 1f)
                    } else {
                        -1f
                    }
                }
                busy = false
                progress = -1f
                ready = file
                launchInstall(file)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                busy = false
                progress = -1f
                line = ""
                error = e.message ?: "下载失败"
            }
        }
    }

    // 无 release 信息（清单字段不全）时只展示一句文案，不提供下载
    if (release == null) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text("检查更新") },
            text = { Text(info.message.ifBlank { "有可用更新，但发布信息不完整，请到官网下载。" }) },
            confirmButton = {
                TextButton(onClick = onDismiss) { Text("知道了") }
            },
        )
        return
    }

    val percent = (progress * 100f).toInt()
    val confirmLabel = when {
        busy -> "正在下载…"
        ready != null -> "立即安装"
        else -> "立即更新"
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = {
            Text(
                text = "发现新版本 " + release.version.ifBlank { info.latest },
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "当前 " + info.current + "　·　新版本体积 " +
                        release.sizeText.ifBlank { "未知" },
                    color = colors.textMuted,
                    fontSize = 12.sp,
                )

                if (release.notes.isNotEmpty()) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 200.dp)
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        release.notes.forEach { note ->
                            Text(
                                text = "· " + note,
                                color = colors.textSecondary,
                                fontSize = 13.sp,
                            )
                        }
                    }
                }

                if (progress >= 0f || busy) {
                    LinearProgressIndicator(
                        progress = { if (progress >= 0f) progress else 0f },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        text = if (line.isBlank()) "$percent%" else "$line · $percent%",
                        color = colors.textMuted,
                        fontSize = 12.sp,
                    )
                }

                error?.let { message ->
                    Text(text = message, color = colors.danger, fontSize = 12.sp)
                }

                if (ready != null && !busy) {
                    Text(
                        text = "安装包已下载并校验通过，点「立即安装」交给系统安装器。",
                        color = colors.textMuted,
                        fontSize = 12.sp,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    val existing = ready
                    if (existing != null && existing.exists() && existing.length() > 0L) {
                        launchInstall(existing)
                    } else if (!Updater.canInstall(context)) {
                        requestInstallPermission()
                    } else {
                        beginDownload(release)
                    }
                },
            ) {
                Text(confirmLabel)
            }
        },
        // 强制更新时不提供「以后再说」
        dismissButton = if (release.mandatory) {
            null
        } else {
            { TextButton(enabled = !busy, onClick = onDismiss) { Text("以后再说") } }
        },
        containerColor = colors.bgCard,
        modifier = Modifier.padding(horizontal = 4.dp),
    )
}
