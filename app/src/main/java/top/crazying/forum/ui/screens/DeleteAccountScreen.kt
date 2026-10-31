package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

private const val MODE_PURGE = "purge"
private const val MODE_ANONYMIZE = "anonymize"

/**
 * 自助注销账号页。
 *
 * 两种方式（彻底删除 / 匿名化保留）+ 密码验证，
 * 需输入当前用户名并二次确认；成功后清空本地登录态并回到登录页。
 */
@Composable
fun DeleteAccountScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    if (!App.isLoggedIn) {
        PageScaffold(title = "注销账号", onBack = { nav.pop() }) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(
                    message = "请先登录后再操作",
                    onRetry = { nav.push(Screen.Auth()) },
                )
            }
        }
        return
    }

    var mode by remember { mutableStateOf(MODE_ANONYMIZE) }
    var password by remember { mutableStateOf("") }
    var confirmName by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var showConfirm by remember { mutableStateOf(false) }

    // ov2 要求输入当前用户名作为二次确认。
    val currentName = App.user.value?.optString("name", "") ?: ""

    fun submit() {
        if (busy) return
        error = ""
        if (currentName.isBlank()) {
            error = "无法获取当前用户名，请重新登录后再试"
            return
        }
        if (confirmName.trim() != currentName) {
            error = "请输入当前用户名「$currentName」以确认"
            return
        }
        if (password.isEmpty()) {
            error = "请输入账号密码"
            return
        }
        showConfirm = true
    }

    fun doDelete() {
        if (busy) return
        scope.launch {
            busy = true
            val r = App.api.deleteAccount(
                mode = mode,
                password = password,
                confirmName = confirmName.trim(),
            )
            busy = false
            showConfirm = false
            if (r.ok) {
                // 清空本地登录态（user_json / cookie_store 等）并回到登录页。
                App.logoutLocal()
                toast(context, "账号已注销")
                nav.pop()
                nav.push(Screen.Auth(false))
            } else {
                error = r.message
            }
        }
    }

    PageScaffold(title = "注销账号", onBack = { nav.pop() }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "注销后账号将无法恢复，请谨慎操作。",
                color = colors.danger,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
            )

            // ── 注销方式 ──
            SectionTitle("注销方式")
            SelectableCard(
                title = "彻底删除",
                desc = "删除账号及你发布的全部帖子、评论、点赞、收藏、关注、举报记录，该操作不可恢复。",
                selected = mode == MODE_PURGE,
                onClick = { mode = MODE_PURGE },
            )
            SelectableCard(
                title = "匿名化保留",
                desc = "删除邮箱、密码等身份信息，用户名统一显示为「已注销用户」，历史帖子与评论正文保留但无法再关联到你。",
                selected = mode == MODE_ANONYMIZE,
                onClick = { mode = MODE_ANONYMIZE },
            )
            Muted("默认选择「匿名化保留」，可随时切换。")

            // ── 身份验证 ──
            SectionTitle("身份验证")
            ForumTextField(
                value = password,
                onValueChange = { password = it },
                placeholder = "请输入账号密码",
                visual = PasswordVisualTransformation(),
            )
            Muted("ov2 只支持密码验证身份，请确认密码无误后再提交。")

            // ── 确认输入 ──
            SectionTitle("确认操作")
            ForumTextField(
                value = confirmName,
                onValueChange = { confirmName = it },
                placeholder = "请输入当前用户名「$currentName」以确认",
            )

            if (error.isNotBlank()) {
                Text(error, color = colors.danger, fontSize = 13.sp)
            }

            GhostButton(
                text = if (busy) "正在注销…" else "确认注销",
                enabled = !busy,
                tint = colors.danger,
                modifier = Modifier.fillMaxWidth(),
                onClick = { submit() },
            )
            Muted("提交后将不可恢复，请确认已备份必要数据。", maxLines = 3)
        }
    }

    if (showConfirm) {
        AlertDialog(
            onDismissRequest = { if (!busy) showConfirm = false },
            title = { Text("确认注销账号") },
            text = {
                Text(
                    text = "你将注销当前账号（" +
                        (if (mode == MODE_PURGE) "彻底删除" else "匿名化保留") +
                        "）。此操作不可恢复，确定继续吗？"
                )
            },
            confirmButton = {
                TextButton(onClick = { doDelete() }, enabled = !busy) {
                    Text(if (busy) "处理中…" else "确认注销", color = colors.danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { showConfirm = false }, enabled = !busy) {
                    Text("取消")
                }
            },
        )
    }
}

/** 单选卡片（注销方式），带圆形选中标记。 */
@Composable
private fun SelectableCard(
    title: String,
    desc: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(if (selected) colors.bgItemActive else colors.bgCard)
            .border(1.dp, if (selected) colors.primary else colors.border, RoundedCornerShape(10.dp))
            .clickable { onClick() }
            .padding(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            modifier = Modifier
                .padding(top = 2.dp)
                .size(16.dp)
                .clip(CircleShape)
                .border(2.dp, if (selected) colors.primary else colors.textMuted, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) {
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(colors.primary),
                )
            }
        }
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(title, color = colors.textPrimary, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(4.dp))
            Text(desc, color = colors.textMuted, fontSize = 12.sp, lineHeight = 18.sp)
        }
    }
}
