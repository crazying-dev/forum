package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

private const val MODE_PURGE = "purge"
private const val MODE_ANONYMIZE = "anonymize"
private const val METHOD_PASSWORD = "password"
private const val METHOD_CODE = "code"
private const val CONFIRM_TEXT = "注销账号"

/**
 * 自助注销账号页。
 *
 * 两种方式（彻底删除 / 匿名化保留）+ 两种身份验证（密码 / 邮箱验证码），
 * 需输入「注销账号」四字并二次确认；成功后清空本地登录态并回到登录页。
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
    var method by remember { mutableStateOf(METHOD_PASSWORD) }
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var confirmText by remember { mutableStateOf("") }
    var countdown by remember { mutableStateOf(0) }
    var sendingCode by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var showConfirm by remember { mutableStateOf(false) }

    // 验证码 60 秒倒计时（禁用「获取验证码」）。
    LaunchedEffect(countdown) {
        if (countdown > 0) {
            delay(1000)
            countdown -= 1
        }
    }

    fun sendCode() {
        if (sendingCode || countdown > 0) return
        error = ""
        sendingCode = true
        scope.launch {
            val r = App.api.sendDeleteAccountCode()
            sendingCode = false
            if (r.ok) {
                countdown = 60
                toast(context, r.message.ifBlank { "验证码已发送至绑定邮箱" })
            } else {
                error = r.message
            }
        }
    }

    fun submit() {
        if (busy) return
        error = ""
        if (confirmText.trim() != CONFIRM_TEXT) {
            error = "请输入「$CONFIRM_TEXT」四字以确认"
            return
        }
        if (method == METHOD_PASSWORD && password.isEmpty()) {
            error = "请输入账号密码"
            return
        }
        if (method == METHOD_CODE && code.trim().isEmpty()) {
            error = "请输入邮箱验证码"
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
                password = if (method == METHOD_PASSWORD) password else null,
                code = if (method == METHOD_CODE) code.trim() else null,
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
            SectionTitle("身份验证（二选一）")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill(
                    text = "账号密码",
                    active = method == METHOD_PASSWORD,
                    onClick = { method = METHOD_PASSWORD },
                )
                Pill(
                    text = "邮箱验证码",
                    active = method == METHOD_CODE,
                    onClick = { method = METHOD_CODE },
                )
            }
            if (method == METHOD_PASSWORD) {
                ForumTextField(
                    value = password,
                    onValueChange = { password = it },
                    placeholder = "请输入账号密码",
                    visual = PasswordVisualTransformation(),
                )
            } else {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    ForumTextField(
                        value = code,
                        onValueChange = { code = it },
                        placeholder = "邮箱验证码",
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    GhostButton(
                        text = when {
                            sendingCode -> "发送中…"
                            countdown > 0 -> "${countdown}s"
                            else -> "获取验证码"
                        },
                        enabled = !sendingCode && countdown == 0,
                        tint = colors.primary,
                        onClick = { sendCode() },
                    )
                }
                Muted("验证码将发送至当前绑定邮箱，5 分钟内有效。")
            }

            // ── 确认输入 ──
            SectionTitle("确认操作")
            ForumTextField(
                value = confirmText,
                onValueChange = { confirmText = it },
                placeholder = "请输入「$CONFIRM_TEXT」以确认",
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
