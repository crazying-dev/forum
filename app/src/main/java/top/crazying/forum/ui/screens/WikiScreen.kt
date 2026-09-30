package top.crazying.forum.ui.screens

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import coil3.compose.AsyncImage
import org.json.JSONObject
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.HDivider
import top.crazying.forum.ui.components.HtmlBody
import top.crazying.forum.ui.components.LoadingBox

/** WIKI 内部页面（WIKI 是底部 tab 根页，子页在本组件内自建回退栈）。 */
private sealed interface WikiPage {
    data object Home : WikiPage
    data object Guanfang : WikiPage
    data object Personal : WikiPage
    data object Mouse : WikiPage
    data object MouseLinux : WikiPage
    data object Live2D : WikiPage
}

/** Linux 版指针主题下载直链（中文文件名需转义）。 */
private val MOUSE_ZIP_URL: String =
    Constants.BASE_URL + "/static/mouse/Liunx/" + Uri.encode("罗小黑战记鼠标Linux版.zip")

/**
 * WIKI：原生 Compose 渲染。
 *
 * 改造前这里是一个全屏 WebView，会连带渲染网页的菜单栏 / 页脚与网页配色。
 * 现在除「Live2D 交互模型」子页（网页 canvas + Live2D 运行时，无法用 Compose 复刻）
 * 之外，其余页面全部用原生组件重写，配色跟随 App 主题（含国庆主题）。
 */
@Composable
fun WikiScreen() {
    val colors = ForumTheme.colors
    val stack = remember { mutableStateListOf<WikiPage>(WikiPage.Home) }
    var live2dReload by remember { mutableStateOf(0) }

    val back: () -> Unit = { if (stack.size > 1) stack.removeAt(stack.lastIndex) }

    BackHandler(enabled = stack.size > 1) { back() }

    Box(modifier = Modifier.fillMaxSize().background(colors.bgBody)) {
        when (stack.last()) {
            WikiPage.Home -> WikiHome(onOpen = { stack.add(it) })
            WikiPage.Guanfang -> WikiSubPage(title = "官方", onBack = back) { WikiGuanfangBody() }
            WikiPage.Personal -> WikiSubPage(title = "个人", onBack = back) {
                WikiPersonalBody(onOpen = { stack.add(it) })
            }
            WikiPage.Mouse -> WikiSubPage(title = "鼠标", onBack = back) {
                WikiMouseBody(onOpen = { stack.add(it) })
            }
            WikiPage.MouseLinux -> WikiSubPage(title = "Linux 版", onBack = back) {
                WikiMouseLinuxBody()
            }
            WikiPage.Live2D -> WikiSubPage(
                title = "Live2D 模型",
                onBack = back,
                actions = {
                    IconButton(onClick = { live2dReload++ }) {
                        Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = colors.textPrimary)
                    }
                },
            ) {
                WikiLive2DBody(reloadToken = live2dReload)
            }
        }
    }
}

// ────────────────── 首页 ──────────────────

@Composable
private fun WikiHome(onOpen: (WikiPage) -> Unit) {
    val colors = ForumTheme.colors
    Column(modifier = Modifier.fillMaxSize().background(colors.bgBody).statusBarsPadding()) {
        Column(modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 8.dp)) {
            Text("WIKI", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold)
            Text("罗小黑战记 · 资料与个人作品", color = colors.textMuted, fontSize = 12.sp)
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Text(
                    text = "罗小黑战记 Wiki",
                    color = colors.textPrimary,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
            item {
                WikiCard(
                    title = "官方",
                    desc = "官方发布的内容信息",
                    imageUrl = Constants.absolute(Constants.WIKI_IMG_DIR + "/guanfang_cover.webp"),
                    onClick = { onOpen(WikiPage.Guanfang) },
                )
            }
            item {
                WikiCard(
                    title = "个人",
                    desc = "用户分享的个人创作",
                    imageUrl = Constants.absolute(Constants.WIKI_IMG_DIR + "/personal_cover.jpg"),
                    onClick = { onOpen(WikiPage.Personal) },
                )
            }
            item { WikiFooterNote() }
        }
    }
}

// ────────────────── 子页骨架 ──────────────────

@Composable
private fun WikiSubPage(
    title: String,
    onBack: () -> Unit,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    val colors = ForumTheme.colors
    Column(modifier = Modifier.fillMaxSize().background(colors.bgBody).statusBarsPadding()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 2.dp, end = 8.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "返回",
                    tint = colors.textPrimary,
                )
            }
            Text(
                text = title,
                color = colors.textPrimary,
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                modifier = Modifier.weight(1f),
            )
            actions()
        }
        HDivider()
        content()
    }
}

// ────────────────── 通用块 ──────────────────

@Composable
private fun WikiHeading(text: String, modifier: Modifier = Modifier) {
    Text(text, color = ForumTheme.colors.textPrimary, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = modifier)
}

@Composable
private fun WikiWarning(text: String) {
    Text(text, color = ForumTheme.colors.danger, fontSize = 14.sp, fontWeight = FontWeight.Medium)
}

@Composable
private fun WikiFooterNote() {
    Text("更多内容持续更新中…", color = ForumTheme.colors.textMuted, fontSize = 12.sp)
}

@Composable
private fun WikiCard(
    title: String,
    desc: String,
    imageUrl: String?,
    onClick: () -> Unit,
) {
    val colors = ForumTheme.colors
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(colors.bgCard)
            .border(1.dp, colors.border, RoundedCornerShape(14.dp))
            .clickable { onClick() },
    ) {
        if (!imageUrl.isNullOrBlank()) {
            AsyncImage(
                model = imageUrl,
                contentDescription = title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(148.dp)
                    .background(colors.bgItemActive),
            )
        }
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, color = colors.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            if (desc.isNotBlank()) Text(desc, color = colors.textSecondary, fontSize = 13.sp)
            Text("查看详情 →", color = colors.textAccent, fontSize = 12.sp)
        }
    }
}

@Composable
private fun WikiDownloadCard(title: String, desc: String, onClick: () -> Unit) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(colors.bgCard)
            .border(1.dp, colors.border, RoundedCornerShape(14.dp))
            .clickable { onClick() }
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.KeyboardArrowDown, contentDescription = null, tint = colors.primary)
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(title, color = colors.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(desc, color = colors.textSecondary, fontSize = 12.sp)
        }
        Text("下载", color = colors.textAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

// ────────────────── 各子页正文 ──────────────────

@Composable
private fun WikiGuanfangBody() {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { WikiHeading("罗小黑战记官方") }
        item { WikiWarning("因为版权问题无法发布") }
        item { WikiFooterNote() }
    }
}

@Composable
private fun WikiPersonalBody(onOpen: (WikiPage) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { WikiHeading("罗小黑战记个人开发") }
        item { WikiWarning("未经授权禁止商用！！") }
        item {
            WikiCard(
                title = "罗小黑战记鼠标",
                desc = "自定义鼠标指针包",
                imageUrl = Constants.absolute(Constants.MOUSE_IMG_DIR + "/banner.png"),
                onClick = { onOpen(WikiPage.Mouse) },
            )
        }
        item {
            WikiCard(
                title = "罗小黑 Live2D 模型（不可下载）",
                desc = "仅供展示 · 点击进入交互预览",
                imageUrl = null,
                onClick = { onOpen(WikiPage.Live2D) },
            )
        }
        item { WikiFooterNote() }
    }
}

@Composable
private fun WikiMouseBody(onOpen: (WikiPage) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { WikiHeading("罗小黑战记鼠标") }
        item { WikiWarning("未经授权禁止商用！！") }
        item {
            WikiCard(
                title = "Linux 版",
                desc = "适用于 GNU/Linux 桌面环境的指针主题",
                imageUrl = Constants.absolute(Constants.MOUSE_IMG_DIR + "/banner.png"),
                onClick = { onOpen(WikiPage.MouseLinux) },
            )
        }
        item { WikiFooterNote() }
    }
}

@Composable
private fun WikiMouseLinuxBody() {
    val context = LocalContext.current
    var readme by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        val text = App.api.fetchText(Constants.MOUSE_README_PATH)
        readme = text
        failed = text == null
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { WikiHeading("罗小黑战记鼠标 - Linux 版") }
        item { WikiWarning("未经授权禁止商用！！") }
        item {
            WikiDownloadCard(
                title = "下载鼠标包",
                desc = "罗小黑战记鼠标 Linux版.zip",
                onClick = { openInBrowser(context, MOUSE_ZIP_URL) },
            )
        }
        item {
            Text(
                text = "提示：该资源面向 GNU/Linux 桌面环境，Android 设备无法直接安装使用。",
                color = ForumTheme.colors.textMuted,
                fontSize = 12.sp,
            )
        }
        item {
            val md = readme
            when {
                md == null && !failed -> LoadingBox()
                failed || md.isNullOrBlank() -> Text(
                    text = "说明文档加载失败，请稍后重试。",
                    color = ForumTheme.colors.textMuted,
                    fontSize = 13.sp,
                )
                else -> HtmlBody(mdToHtml(md))
            }
        }
    }
}

// ────────────────── Live2D（去壳 WebView） ──────────────────

private const val LIVE2D_DECHROME_ID = "crforum-dechrome"

/**
 * Live2D 交互模型：网页 canvas + Live2D 运行时，Compose 无法复刻，
 * 因此仍用 WebView，但注入样式剥掉网页外壳（头部/侧边栏/页脚/公告），
 * 并把 CSS 变量改写为 App 当前配色，视觉上与原生页一致。
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun WikiLive2DBody(reloadToken: Int) {
    val colors = ForumTheme.colors
    val bg = cssHex(colors.bgBody)
    val css = buildString {
        append("header.header,nav.side-nav,#sideNav,#settingDropdown,.side-setting-dropdown,")
        append(".site-announce,footer.footer,.world-panel,#global-live2d{display:none!important;}")
        append("html,body{margin:0!important;padding:0!important;background:").append(bg).append("!important;}")
        append(".layout,.layout-main{margin:0!important;padding:0!important;}")
        append(":root{")
        append("--color-bg-body:").append(bg).append(";")
        append("--color-bg-header:").append(cssHex(colors.bgHeader)).append(";")
        append("--color-bg-card:").append(cssHex(colors.bgCard)).append(";")
        append("--color-text-primary:").append(cssHex(colors.textPrimary)).append(";")
        append("--color-text-secondary:").append(cssHex(colors.textSecondary)).append(";")
        append("--color-primary:").append(cssHex(colors.primary)).append(";")
        append("--color-border:").append(cssHex(colors.border)).append(";")
        append("}")
    }
    val inject = "(function(){var id='" + LIVE2D_DECHROME_ID + "';" +
        "var old=document.getElementById(id);if(old){old.remove();}" +
        "var s=document.createElement('style');s.id=id;s.textContent=" + JSONObject.quote(css) + ";" +
        "(document.head||document.documentElement).appendChild(s);" +
        "var m=document.querySelector('meta[name=\"theme-color\"]');if(m){m.setAttribute('content','" + bg + "');}" +
        "})();"

    key(reloadToken) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.useWideViewPort = true
                    settings.loadWithOverviewMode = true
                    setBackgroundColor(colors.bgBody.toArgb())
                    webViewClient = object : WebViewClient() {
                        override fun onPageFinished(view: WebView, url: String) {
                            view.evaluateJavascript(inject, null)
                        }
                    }
                    loadUrl(Constants.LIVE2D_URL)
                }
            },
            onRelease = { view -> runCatching { view.destroy() } },
        )
    }
}

// ────────────────── 工具 ──────────────────

/** Compose 颜色 → CSS `#RRGGBB`。 */
private fun cssHex(color: Color): String = String.format("#%06X", 0xFFFFFF and color.toArgb())

private fun openInBrowser(context: Context, url: String) {
    runCatching {
        context.startActivity(
            Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}

// ────────────────── 极简 Markdown → HTML（仅覆盖 WIKI 说明文档用到的语法） ──────────────────

private fun mdEscape(s: String): String =
    s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

private fun mdInline(s: String): String {
    var t = mdEscape(s)
    // ![alt](url) → 只保留 alt（图片在客户端不展示）
    t = Regex("!\\[([^\\]]*)\\]\\(([^)]*)\\)").replace(t) { it.groupValues[1] }
    // [text](url) → <a>
    t = Regex("\\[([^\\]]+)\\]\\(([^)]+)\\)").replace(t) { m ->
        "<a href=\"" + m.groupValues[2] + "\">" + m.groupValues[1] + "</a>"
    }
    // **bold**
    t = Regex("\\*\\*([^*]+)\\*\\*").replace(t) { m -> "<b>" + m.groupValues[1] + "</b>" }
    // `code`
    t = Regex("`([^`]+)`").replace(t) { m -> "<code>" + m.groupValues[1] + "</code>" }
    return t
}

/** 把 README 这类简单 Markdown 转成 HtmlCompat 能渲染的 HTML。 */
private fun mdToHtml(md: String): String {
    val out = StringBuilder()
    val lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    var inCode = false
    val code = StringBuilder()
    val para = StringBuilder()
    var listOpen = false

    fun flushPara() {
        if (para.isNotEmpty()) {
            out.append("<p>").append(mdInline(para.toString())).append("</p>")
            para.setLength(0)
        }
    }

    fun closeList() {
        if (listOpen) {
            out.append("</ul>")
            listOpen = false
        }
    }

    for (raw in lines) {
        val line = raw.trimEnd()
        if (line.trimStart().startsWith("```")) {
            if (inCode) {
                out.append("<pre>").append(mdEscape(code.toString())).append("</pre>")
                code.setLength(0)
                inCode = false
            } else {
                flushPara()
                closeList()
                inCode = true
            }
            continue
        }
        if (inCode) {
            code.append(raw).append('\n')
            continue
        }
        val t = line.trim()
        when {
            t.isEmpty() -> {
                flushPara()
                closeList()
            }
            t.startsWith("####") -> {
                flushPara(); closeList()
                out.append("<h4>").append(mdInline(t.trimStart('#').trim())).append("</h4>")
            }
            t.startsWith("###") -> {
                flushPara(); closeList()
                out.append("<h3>").append(mdInline(t.trimStart('#').trim())).append("</h3>")
            }
            t.startsWith("##") -> {
                flushPara(); closeList()
                out.append("<h2>").append(mdInline(t.trimStart('#').trim())).append("</h2>")
            }
            t.startsWith("#") -> {
                flushPara(); closeList()
                out.append("<h1>").append(mdInline(t.trimStart('#').trim())).append("</h1>")
            }
            t.startsWith("---") || t.startsWith("***") -> {
                flushPara(); closeList()
                out.append("<hr>")
            }
            t.startsWith(">") -> {
                flushPara(); closeList()
                out.append("<blockquote>").append(mdInline(t.trimStart('>').trim())).append("</blockquote>")
            }
            t.startsWith("- ") || t.startsWith("* ") -> {
                flushPara()
                if (!listOpen) {
                    out.append("<ul>")
                    listOpen = true
                }
                out.append("<li>").append(mdInline(t.substring(2).trim())).append("</li>")
            }
            Regex("^\\d+\\.\\s").containsMatchIn(t) -> {
                flushPara()
                if (!listOpen) {
                    out.append("<ul>")
                    listOpen = true
                }
                out.append("<li>").append(mdInline(t.substringAfter(' ').trim())).append("</li>")
            }
            else -> {
                closeList()
                if (para.isNotEmpty()) para.append(' ')
                para.append(t)
            }
        }
    }
    if (inCode && code.isNotEmpty()) {
        out.append("<pre>").append(mdEscape(code.toString())).append("</pre>")
    }
    flushPara()
    closeList()
    return out.toString()
}
