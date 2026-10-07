package top.crazying.forum.ui.screens

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.core.WebAuth
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.GhostButton
import top.crazying.forum.ui.components.toast

/**
 * 网页端登录：在内置 WebView 里加载站点**真实登录页**（`/auth?mode=login`）。
 *
 * 为什么这么做：官方 Turnstile 在真实网页里渲染，不受我们内嵌承载页
 * （`/captcha-embed`）的 WebView 层级 / 命中区问题影响；登录成功后服务端下发
 * `token` + `ID` 两个 HttpOnly Cookie，把它们搬进 App 的 OkHttp CookieJar，
 * 会话即迁移完成——后续接口依旧走原生请求。
 *
 * 注意：站点登录是 `fetch('/api/user/login')` **不会触发页面跳转**，
 * 所以不能只靠 `onPageFinished` 判断成功，必须定时读 `CookieManager`。
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WebLoginScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val siteUrl = remember { WebAuth.siteUrl(Constants.BASE_URL) }

    var done by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("请在下方网页中登录，登录成功会自动返回。") }

    /** 读 WebView Cookie → 搬进 App 会话 → 拉一次用户信息验证。 */
    suspend fun tryAdopt(): Boolean {
        val header = runCatching { CookieManager.getInstance().getCookie(siteUrl) }.getOrNull()
        if (!WebAuth.hasSession(header)) return false
        if (App.api.importWebCookies(header ?: "") <= 0) return false
        if (App.api.me().ok) return true
        // Cookie 拿到了但服务端不认（已过期等）：清掉重来，避免死循环。
        runCatching { App.api.clearCookies() }
        return false
    }

    /** 登录成功后的统一收尾：提示 + 退回（登录页也一并弹掉）。 */
    fun finishLogin() {
        done = true
        toast(context, "登录成功")
        nav.pop()
        if (nav.current is Screen.Auth) nav.pop()
    }

    LaunchedEffect(Unit) {
        while (!done) {
            delay(1200)
            if (busy) continue
            if (tryAdopt()) {
                finishLogin()
                return@LaunchedEffect
            }
        }
    }

    /** 手动重试（定时轮询漏掉时用）：逻辑与轮询完全一致。 */
    fun adoptManually() {
        if (busy || done) return
        scope.launch {
            busy = true
            note = "正在获取登录状态…"
            if (tryAdopt()) {
                finishLogin()
            } else {
                note = "还没检测到登录状态，请在网页里完成登录后再点「我已完成」。"
            }
            busy = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            GhostButton(text = "返回", onClick = { nav.pop() })
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "网页登录",
                    color = colors.textPrimary,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(text = note, color = colors.textMuted, fontSize = 12.sp)
            }
            TextButton(enabled = !done, onClick = { adoptManually() }) {
                Text("我已完成", color = colors.primary)
            }
        }

        AndroidView(
            modifier = Modifier
                .fillMaxSize()
                .imePadding(),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.useWideViewPort = true
                    settings.loadWithOverviewMode = true
                    settings.javaScriptCanOpenWindowsAutomatically = true
                    settings.setSupportMultipleWindows(false)
                    settings.databaseEnabled = true
                    CookieManager.getInstance().setAcceptCookie(true)
                    CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                    webViewClient = WebViewClient()
                    loadUrl(WebAuth.loginUrl(Constants.BASE_URL))
                }
            },
            onRelease = { view -> runCatching { view.destroy() } },
        )
    }
}
