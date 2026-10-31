package top.crazying.forum.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import top.crazying.forum.core.App
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

private const val GENDER_UNSET = 0
private const val GENDER_MALE = 1
private const val GENDER_FEMALE = 2

private val EMAIL_RE = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")

/** 从服务端 `age`（YYYYMMDD / YYYY-MM-DD / YYYY）解析出生日期；无法解析返回 null。 */
private fun parseBirth(raw: String): Triple<Int, Int, Int>? {
    val digits = raw.filter { it.isDigit() }
    return when {
        digits.length >= 8 -> {
            val y = digits.substring(0, 4).toIntOrNull() ?: return null
            val m = digits.substring(4, 6).toIntOrNull() ?: return null
            val d = digits.substring(6, 8).toIntOrNull() ?: return null
            if (m in 1..12 && d in 1..31) Triple(y, m, d) else null
        }
        digits.length == 4 -> Triple(digits.toInt(), 1, 1)
        else -> null
    }
}

/** 当月天数（闰年正确）。 */
private fun daysInMonth(year: Int, month: Int): Int {
    val cal = java.util.Calendar.getInstance()
    cal.set(year, month - 1, 1)
    return cal.getActualMaximum(java.util.Calendar.DAY_OF_MONTH)
}

/**
 * 「编辑资料」页：资料（头像 / 昵称 / 性别 / 出生日期 / 简介）+ 账号安全（修改密码 / 更换绑定邮箱）。
 *
 * 对齐网页端「编辑资料」面板；头像随选随传，其余字段点「保存」一次提交（`PATCH /ov2/api/users/me`）。
 * 出生日期仅在用户确实改动时才提交，避免把默认的 2000-01-01 误写入资料。
 * 修改密码校验当前密码；更换邮箱走「验证当前邮箱 → 验证新邮箱」四步向导。
 */
@Composable
fun ProfileEditScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    if (!App.isLoggedIn) {
        PageScaffold(title = "编辑资料", onBack = { nav.pop() }) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(message = "请先登录后再编辑资料", onRetry = { nav.push(Screen.Auth()) })
            }
        }
        return
    }

    val me = App.user.value
    val currentEmail = me?.optString("email", "") ?: ""

    val currentYear = remember { java.util.Calendar.getInstance().get(java.util.Calendar.YEAR) }
    val yearOptions = remember(currentYear) { (currentYear downTo 1900).map { it.toString() to it } }
    val monthOptions = remember { (1..12).map { "%02d".format(it) to it } }

    // ── 基本资料 ──
    var name by remember { mutableStateOf(me?.optString("name", "") ?: "") }
    var gender by remember { mutableStateOf(me?.optInt("gender", 0) ?: 0) }
    var intro by remember { mutableStateOf(me?.optString("intro", "") ?: "") }

    // ── 出生日期 ──
    val initialBirth = remember { parseBirth(me?.optString("age", "") ?: "") }
    var year by remember { mutableStateOf(initialBirth?.first ?: 2000) }
    var month by remember { mutableStateOf(initialBirth?.second ?: 1) }
    var day by remember { mutableStateOf(initialBirth?.third ?: 1) }
    var noBirth by remember { mutableStateOf((me?.optString("age", "") ?: "").isBlank()) }
    var birthTouched by remember { mutableStateOf(false) }

    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var uploading by remember { mutableStateOf(false) }

    // ── 修改密码 ──
    var showPwd by remember { mutableStateOf(false) }
    var pwdCurrent by remember { mutableStateOf("") }
    var pwdNew by remember { mutableStateOf("") }
    var pwdNew2 by remember { mutableStateOf("") }
    var pwdBusy by remember { mutableStateOf(false) }
    var pwdError by remember { mutableStateOf("") }

    // ── 更换邮箱（四步向导：1 发旧码、2 验旧码、3 发新码、4 确认换绑） ──
    var showEmail by remember { mutableStateOf(false) }
    var emailStep by remember { mutableStateOf(1) }
    var oldCode by remember { mutableStateOf("") }
    var newEmail by remember { mutableStateOf("") }
    var newCode by remember { mutableStateOf("") }
    var oldCountdown by remember { mutableStateOf(0) }
    var newCountdown by remember { mutableStateOf(0) }
    var oldSending by remember { mutableStateOf(false) }
    var newSending by remember { mutableStateOf(false) }
    var emailBusy by remember { mutableStateOf(false) }
    var emailError by remember { mutableStateOf("") }

    LaunchedEffect(oldCountdown) { if (oldCountdown > 0) { delay(1000); oldCountdown -= 1 } }
    LaunchedEffect(newCountdown) { if (newCountdown > 0) { delay(1000); newCountdown -= 1 } }

    val pickImage = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = runCatching {
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            }.getOrNull()
            if (bytes == null) { toast(context, "读取图片失败"); return@launch }
            if (bytes.size > 5 * 1024 * 1024) { toast(context, "图片不能超过 5MB"); return@launch }
            val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
            val ext = when { mime.contains("png") -> "png"; mime.contains("webp") -> "webp"; else -> "jpg" }
            uploading = true
            val r = App.api.uploadAvatar(bytes, "avatar.$ext", mime)
            uploading = false
            if (r.ok) {
                runCatching { App.api.me() }
                toast(context, "头像已更新")
            } else {
                toast(context, r.message)
            }
        }
    }

    fun save() {
        if (saving) return
        error = ""
        val n = name.trim()
        if (n.isEmpty()) { error = "昵称不能为空"; return }
        saving = true
        scope.launch {
            val body = JSONObject().put("name", n).put("gender", gender).put("intro", intro.trim())
            if (birthTouched) {
                body.put("age", if (noBirth) "" else "%04d%02d%02d".format(year, month, day))
            }
            val r = App.api.updateProfile(body)
            saving = false
            if (r.ok) { toast(context, "资料已保存"); nav.pop() } else error = r.message
        }
    }

    fun submitPwd() {
        if (pwdBusy) return
        pwdError = ""
        if (pwdCurrent.isEmpty()) { pwdError = "请输入当前密码"; return }
        if (pwdNew.isBlank()) { pwdError = "请输入新密码"; return }
        if (pwdNew != pwdNew2) { pwdError = "两次输入的新密码不一致"; return }
        pwdBusy = true
        scope.launch {
            val r = App.api.changePassword(pwdCurrent, pwdNew)
            pwdBusy = false
            if (r.ok) {
                pwdCurrent = ""; pwdNew = ""; pwdNew2 = ""
                // 服务端会为当前会话重签 Cookie，本机保持登录，其他设备退出。
                toast(context, "密码已修改，其他设备已退出登录")
            } else pwdError = r.message
        }
    }

    /** 第 1 步：向当前绑定邮箱发验证码。 */
    fun sendOldCode() {
        if (oldSending || oldCountdown > 0) return
        emailError = ""
        oldSending = true
        scope.launch {
            val r = App.api.sendChangeEmailOldCode()
            oldSending = false
            if (r.ok) { oldCountdown = 60; toast(context, r.message.ifBlank { "验证码已发送至当前邮箱" }) }
            else emailError = r.message
        }
    }

    /** 第 2 步：验证当前邮箱验证码，成功后进入第 3 步。 */
    fun verifyOldCode() {
        if (emailBusy) return
        emailError = ""
        val code = oldCode.trim()
        if (code.isEmpty()) { emailError = "请输入当前邮箱验证码"; return }
        emailBusy = true
        scope.launch {
            emailStep = 2
            val r = App.api.verifyChangeEmailOld(code)
            emailBusy = false
            if (r.ok) {
                emailStep = 3
                toast(context, "当前邮箱已验证")
            } else {
                emailStep = 1
                emailError = r.message
            }
        }
    }

    /** 第 3 步：向新邮箱发验证码。 */
    fun sendNewCode() {
        if (newSending || newCountdown > 0) return
        emailError = ""
        val target = newEmail.trim()
        if (!EMAIL_RE.matches(target)) { emailError = "请输入有效的新邮箱地址"; return }
        newSending = true
        scope.launch {
            val r = App.api.sendChangeEmailNewCode(target)
            newSending = false
            if (r.ok) {
                newCountdown = 60
                emailStep = 4
                toast(context, r.message.ifBlank { "验证码已发送至新邮箱" })
            } else emailError = r.message
        }
    }

    /** 第 4 步：凭新邮箱验证码完成换绑。 */
    fun submitEmail() {
        if (emailBusy) return
        emailError = ""
        val code = newCode.trim()
        if (code.isEmpty()) { emailError = "请输入新邮箱验证码"; return }
        emailBusy = true
        scope.launch {
            val r = App.api.confirmChangeEmail(code)
            emailBusy = false
            if (r.ok) {
                oldCode = ""; newCode = ""; newEmail = ""
                emailStep = 1
                toast(context, "绑定邮箱已更换")
                showEmail = false
                runCatching { App.api.me() }
            } else emailError = r.message
        }
    }

    PageScaffold(title = "编辑资料", onBack = { nav.pop() }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // ── 头像 ──
            SectionTitle("头像")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(App.user.value?.optString("avatar", ""), 72.dp)
                Spacer(Modifier.width(14.dp))
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    GhostButton(
                        text = if (uploading) "上传中…" else "更换头像",
                        enabled = !uploading,
                        onClick = { pickImage.launch("image/*") },
                    )
                    Muted("支持 JPG / PNG / WebP，不超过 5MB，自动裁剪为方形。", maxLines = 2)
                }
            }

            HDivider()

            // ── 基本资料 ──
            SectionTitle("基本资料")
            Muted("昵称", maxLines = 1)
            ForumTextField(value = name, onValueChange = { name = it }, placeholder = "请输入昵称")

            Muted("性别", maxLines = 1)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill("未设置", active = gender == GENDER_UNSET) { gender = GENDER_UNSET }
                Pill("男", active = gender == GENDER_MALE) { gender = GENDER_MALE }
                Pill("女", active = gender == GENDER_FEMALE) { gender = GENDER_FEMALE }
            }

            Muted("出生日期", maxLines = 1)
            val dayCount = daysInMonth(year, month)
            val safeDay = day.coerceAtMost(dayCount)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DropdownField(
                    label = year.toString(),
                    options = yearOptions,
                    selected = year,
                    enabled = !noBirth,
                    onSelect = { v ->
                        year = v
                        if (day > daysInMonth(v, month)) day = daysInMonth(v, month)
                        noBirth = false
                        birthTouched = true
                    },
                    modifier = Modifier.weight(1.4f),
                )
                DropdownField(
                    label = "%02d".format(month),
                    options = monthOptions,
                    selected = month,
                    enabled = !noBirth,
                    onSelect = { v ->
                        month = v
                        if (day > daysInMonth(year, v)) day = daysInMonth(year, v)
                        noBirth = false
                        birthTouched = true
                    },
                    modifier = Modifier.weight(1f),
                )
                DropdownField(
                    label = "%02d".format(safeDay),
                    options = (1..dayCount).map { "%02d".format(it) to it },
                    selected = safeDay,
                    enabled = !noBirth,
                    onSelect = { v -> day = v; noBirth = false; birthTouched = true },
                    modifier = Modifier.weight(1f),
                )
            }
            Pill(
                text = if (noBirth) "不展示出生日期 ✓" else "不展示出生日期",
                active = noBirth,
                onClick = { noBirth = !noBirth; birthTouched = true },
            )

            Muted("简介", maxLines = 1)
            ForumTextField(
                value = intro,
                onValueChange = { if (it.length <= 500) intro = it },
                placeholder = "介绍一下自己吧（不超过 500 字）",
                singleLine = false,
                minHeight = 80.dp,
            )

            if (error.isNotBlank()) Text(error, color = colors.danger, fontSize = 13.sp)

            PrimaryButton(
                text = if (saving) "正在保存…" else "保存资料",
                enabled = !saving,
                modifier = Modifier.fillMaxWidth(),
                onClick = { save() },
            )

            HDivider()

            // ── 账号安全 ──
            SectionTitle("账号安全")
            Muted("修改密码需验证当前密码；更换绑定邮箱需依次验证当前邮箱与新邮箱。", maxLines = 3)

            GhostButton(
                text = if (showPwd) "修改密码 ▲" else "修改密码 ▼",
                modifier = Modifier.fillMaxWidth(),
                onClick = { showPwd = !showPwd; pwdError = "" },
            )
            if (showPwd) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    ForumTextField(
                        value = pwdCurrent,
                        onValueChange = { pwdCurrent = it },
                        placeholder = "当前密码",
                        visual = PasswordVisualTransformation(),
                    )
                    ForumTextField(
                        value = pwdNew,
                        onValueChange = { pwdNew = it },
                        placeholder = "新密码",
                        visual = PasswordVisualTransformation(),
                    )
                    ForumTextField(
                        value = pwdNew2,
                        onValueChange = { pwdNew2 = it },
                        placeholder = "确认新密码",
                        visual = PasswordVisualTransformation(),
                    )
                    if (pwdError.isNotBlank()) Text(pwdError, color = colors.danger, fontSize = 13.sp)
                    GhostButton(
                        text = if (pwdBusy) "提交中…" else "确认修改密码",
                        enabled = !pwdBusy,
                        tint = colors.primary,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { submitPwd() },
                    )
                    Muted("修改成功后本机保持登录，其他设备会被退出登录。", maxLines = 3)
                }
            }

            GhostButton(
                text = if (showEmail) "更换绑定邮箱 ▲" else "更换绑定邮箱 ▼",
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    showEmail = !showEmail
                    emailError = ""
                    if (!showEmail) { emailStep = 1; oldCode = ""; newCode = "" }
                },
            )
            if (showEmail) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    when (emailStep) {
                        1 -> {
                            Muted("第 1 步 / 共 4 步 · 当前绑定邮箱：$currentEmail", maxLines = 2)
                            GhostButton(
                                text = when {
                                    oldSending -> "发送中…"
                                    oldCountdown > 0 -> "${oldCountdown}s"
                                    else -> "发送验证码到当前邮箱"
                                },
                                enabled = !oldSending && oldCountdown == 0,
                                tint = colors.primary,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { sendOldCode() },
                            )
                            ForumTextField(
                                value = oldCode,
                                onValueChange = { oldCode = it },
                                placeholder = "当前邮箱验证码",
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            )
                            if (emailError.isNotBlank()) Text(emailError, color = colors.danger, fontSize = 13.sp)
                            GhostButton(
                                text = if (emailBusy) "验证中…" else "验证当前邮箱",
                                enabled = !emailBusy,
                                tint = colors.primary,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { verifyOldCode() },
                            )
                        }
                        2 -> Muted("第 2 步 / 共 4 步 · 正在验证当前邮箱…", maxLines = 2)
                        3 -> {
                            Muted("第 3 步 / 共 4 步 · 当前邮箱已验证，请输入新邮箱", maxLines = 2)
                            ForumTextField(
                                value = newEmail,
                                onValueChange = { newEmail = it },
                                placeholder = "新邮箱地址",
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            )
                            if (emailError.isNotBlank()) Text(emailError, color = colors.danger, fontSize = 13.sp)
                            GhostButton(
                                text = when {
                                    newSending -> "发送中…"
                                    newCountdown > 0 -> "${newCountdown}s"
                                    else -> "发送验证码到新邮箱"
                                },
                                enabled = !newSending && newCountdown == 0,
                                tint = colors.primary,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { sendNewCode() },
                            )
                        }
                        else -> {
                            Muted("第 4 步 / 共 4 步 · 验证码已发送至 $newEmail", maxLines = 2)
                            ForumTextField(
                                value = newCode,
                                onValueChange = { newCode = it },
                                placeholder = "新邮箱验证码",
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            )
                            if (emailError.isNotBlank()) Text(emailError, color = colors.danger, fontSize = 13.sp)
                            GhostButton(
                                text = if (emailBusy) "提交中…" else "确认换绑",
                                enabled = !emailBusy,
                                tint = colors.primary,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { submitEmail() },
                            )
                            GhostButton(
                                text = "重新填写新邮箱",
                                enabled = !newSending,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { emailStep = 3; newCode = ""; emailError = "" },
                            )
                        }
                    }
                }
            }

            HDivider()
            GhostButton(
                text = "注销账号",
                tint = colors.danger,
                modifier = Modifier.fillMaxWidth(),
                onClick = { nav.push(Screen.DeleteAccount) },
            )
            Muted("妖精论坛 · 我们仅收集实现功能所必需的数据。", maxLines = 3)
        }
    }
}

/** 单个下拉选择框（年 / 月 / 日），沿用应用色板。 */
@Composable
private fun DropdownField(
    label: String,
    options: List<Pair<String, Int>>,
    selected: Int,
    enabled: Boolean,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    var expanded by remember { mutableStateOf(false) }
    Box(modifier = modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(colors.bgInput)
                .border(1.dp, colors.border, RoundedCornerShape(10.dp))
                .clickable(enabled = enabled) { expanded = true }
                .padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = label,
                color = if (enabled) colors.textPrimary else colors.textMuted,
                fontSize = 14.sp,
                modifier = Modifier.weight(1f),
            )
            Text("v", color = colors.textMuted, fontSize = 11.sp)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (text, value) ->
                DropdownMenuItem(
                    text = {
                        Text(
                            text = text,
                            color = if (value == selected) colors.primary else colors.textPrimary,
                        )
                    },
                    onClick = {
                        expanded = false
                        onSelect(value)
                    },
                )
            }
        }
    }
}
