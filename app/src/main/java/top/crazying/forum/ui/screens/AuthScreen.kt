package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
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
import top.crazying.forum.core.askCaptcha
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.components.ForumTextField
import top.crazying.forum.ui.components.GhostButton
import top.crazying.forum.ui.components.PrimaryButton
import top.crazying.forum.ui.components.toast

/**
 * 登录 / 注册页。
 *
 * 本轮注册走「用户名 + 邮箱 + 密码」的直注（服务端仍然支持验证码注册，
 * 但邮箱验证码注册流程排到下一轮，见 README「后续计划」）。
 */
@Composable
fun AuthScreen(nav: Navigator, startRegister: Boolean = false) {
    var register by remember { mutableStateOf(startRegister) }
    var account by remember { mutableStateOf(App.prefs.lastName) }
    var email by remember { mutableStateOf("" ) }
    var password by remember { mutableStateOf("") }
    var password2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }

    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val colors = ForumTheme.colors

    fun submit() {
        if (busy) return
        error = ""
        if (register) {
            val name = account.trim()
            if (name.length < 2 || name.length > 20) {
                error = "用户名长度需为 2~20 个字符"
                return
            }
            if (!email.contains("@")) {
                error = "请填写正确的邮箱"
                return
            }
            if (password.length < 8 || !password.any { it.isLetter() } || !password.any { it.isDigit() }) {
                error = "密码至少 8 位，且需同时包含字母和数字"
                return
            }
            if (password != password2) {
                error = "两次输入的密码不一致"
                return
            }
        } else if (account.isBlank() || password.isEmpty()) {
            error = "请填写账号与密码"
            return
        }

        busy = true
        scope.launch {
            // 人机验证（服务端未启用时返回空串，直接继续）。用户取消则中断本次登录/注册。
            val captchaToken = askCaptcha()
            if (captchaToken == null) {
                busy = false
                return@launch
            }
            val result = if (register) {
                App.api.register(account.trim(), email.trim(), password, captchaToken)
            } else {
                val key = account.trim()
                if (key.contains("@")) {
                    App.api.login(email = key, password = password, captchaToken = captchaToken)
                } else {
                    App.api.login(name = key, password = password, captchaToken = captchaToken)
                }
            }
            busy = false
            if (result.ok) {
                toast(context, if (register) "注册成功" else "登录成功")
                nav.pop()
            } else {
                error = result.message
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding()
            .imePadding(),
    ) {
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GhostButton(text = "返回", onClick = { nav.pop() })
        }

        Spacer(Modifier.height(28.dp))

        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "妖精论坛",
                color = colors.primary,
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = if (register) "注册一个新帐号" else "登录后即可发帖、评论与收藏",
                color = colors.textMuted,
                fontSize = 13.sp,
            )
        }

        Spacer(Modifier.height(22.dp))

        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ForumTextField(
                value = account,
                onValueChange = { account = it },
                placeholder = if (register) "用户名（2~20 字符）" else "用户名 / 邮箱",
            )
            if (register) {
                ForumTextField(
                    value = email,
                    onValueChange = { email = it },
                    placeholder = "邮箱",
                )
            }
            ForumTextField(
                value = password,
                onValueChange = { password = it },
                placeholder = if (register) "密码（至少 8 位，含字母与数字）" else "密码",
                visual = PasswordVisualTransformation(),
            )
            if (register) {
                ForumTextField(
                    value = password2,
                    onValueChange = { password2 = it },
                    placeholder = "确认密码",
                    visual = PasswordVisualTransformation(),
                )
            }

            if (error.isNotBlank()) {
                Text(text = error, color = colors.danger, fontSize = 13.sp)
            }

            Spacer(Modifier.height(2.dp))

            PrimaryButton(
                text = if (busy) "请稍候…" else if (register) "注册并登录" else "登录",
                onClick = { submit() },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(6.dp))

            Box(
                modifier = Modifier.fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                val tip = if (register) "已有帐号？去登录" else "还没有帐号？去注册"
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .clickable {
                            register = !register
                            error = ""
                        }
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                ) {
                    Text(text = tip, color = colors.primary, fontSize = 13.sp)
                }
            }
        }
    }
}
