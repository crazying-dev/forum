package top.crazying.forum.ui.screens

import android.annotation.SuppressLint
import android.graphics.Color as AndroidColor
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme

/**
 * WIKI 页：直接把 Web 端的 `/WIKI` 页丢进 WebView。
 *
 * 这是全工程唯一使用 WebView 的地方（见 README「技术选型」），
 * 因为 WIKI 是大量图文混排的静态长页，用 Compose 重写性价比很低。
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WikiScreen() {
    val colors = ForumTheme.colors
    var webView by remember { mutableStateOf<WebView?>(null) }
    var reloadToken by remember { mutableStateOf(0) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("WIKI", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                Text("罗小黑战记 · 资料与个人作品", color = colors.textMuted, fontSize = 12.sp)
            }
            IconButton(
                onClick = {
                    val view = webView
                    if (view != null) view.reload() else reloadToken++
                },
            ) {
                Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = colors.textPrimary)
            }
        }

        key(reloadToken) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    WebView(ctx).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.useWideViewPort = true
                        settings.loadWithOverviewMode = true
                        settings.textZoom = 100
                        setBackgroundColor(AndroidColor.TRANSPARENT)
                        webViewClient = WebViewClient()
                        loadUrl(Constants.WIKI_URL)
                        webView = this
                    }
                },
                onRelease = { view ->
                    webView = null
                    runCatching { view.destroy() }
                },
            )
        }
    }
}
