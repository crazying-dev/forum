package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.core.WorldFeed
import top.crazying.forum.core.takeCodePoints
import top.crazying.forum.core.richtext.RichDocument
import top.crazying.forum.core.richtext.RichHtml
import top.crazying.forum.data.WorldMessage
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*
import top.crazying.forum.ui.richtext.RichTextView
import java.util.concurrent.atomic.AtomicInteger

/**
 * 世界频道单条消息上限（Unicode 码点）：
 * 与服务端 `worldMaxContentRunes`（2000）一致；按码点截断不会切断 emoji 代理对。
 */
private const val WORLD_TEXT_MAX_CHARS = 2000

/**
 * 世界频道。
 *
 * 本轮用「拉取 `/ov2/api/world/messages` + 20 秒轮询」而不是 WebSocket，
 * 好处是不必引入长连接与重连状态机，代价是消息有最多 20 秒延迟（已在 README 标注）。
 *
 * 发送只支持**纯文本**：底部直接内联输入框，不再打开全屏富文本编辑器。
 * 历史消息仍是富文本 HTML（可能含图片），气泡内继续用 [RichTextView] 渲染。
 */
@Composable
fun WorldScreen(nav: Navigator, store: FeedStateStore, scope: CoroutineScope) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val meId = App.userId
    val listState = rememberLazyListState()

    // 草稿 / 发送状态放在根节点持有的 store 里：切 tab、点进用户主页再回来都不丢。
    val ws = store.world

    var messages by remember { mutableStateOf<List<WorldMessage>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    /** 列表请求序号：只采用最后一次请求的响应，避免轮询/手动刷新互相覆盖。 */
    val loadSeq = remember { AtomicInteger(0) }
    /** 需要在下一帧把列表滚到底（首次加载 / 刚发完消息）。 */
    var pendingScrollToBottom by remember { mutableStateOf(false) }

    // 键盘弹出时列表视口变矮，聊天页面应保持最新消息可见。
    val density = LocalDensity.current
    val keyboardVisible = WindowInsets.ime.getBottom(density) > 0
    LaunchedEffect(keyboardVisible) {
        if (keyboardVisible && messages.isNotEmpty()) {
            runCatching { listState.scrollToItem(messages.lastIndex) }
        }
    }

    // 列表更新后再滚动：此时 LazyColumn 已经拿到新数据，scrollToItem 才生效。
    LaunchedEffect(messages) {
        if (pendingScrollToBottom && messages.isNotEmpty()) {
            pendingScrollToBottom = false
            runCatching { listState.scrollToItem(messages.lastIndex) }
        }
    }

    suspend fun load(silent: Boolean = false, toBottom: Boolean = false) {
        val seq = loadSeq.incrementAndGet()
        if (!silent) loading = true
        val result = App.api.worldAll()
        // 期间又发起了新请求：本次响应已过期，直接丢弃。
        if (seq != loadSeq.get()) return
        if (!silent) loading = false
        if (!result.ok) {
            if (!silent) error = result.message
            return
        }
        error = ""
        // ov2 返回 `{success, items, has_more, next_before_id}`。
        val list = WorldMessage.list(result.rows("items"))
        // 服务端按时间**倒序**返回（最新在前）；这里转成聊天顺序（最新在下），
        // 并保留最新的 WORLD_LIMIT 条。口径集中在 WorldFeed，便于单测。
        messages = WorldFeed.newestLast(list, Constants.WORLD_LIMIT)
        if (toBottom) pendingScrollToBottom = true
    }

    LaunchedEffect(Unit) { load(toBottom = true) }

    // 自动轮询（服务端有 2 秒/人 的发送限流，20 秒足够温和）
    LaunchedEffect(Unit) {
        while (true) {
            delay(20_000)
            load(silent = true)
        }
    }

    /** 发送纯文本：未登录先去登录页；成功后清空草稿并刷新到最新。 */
    fun send() {
        if (ws.sending) return
        if (!App.isLoggedIn) {
            toast(context, "请先登录")
            nav.push(Screen.Auth())
            return
        }
        val text = ws.draft.trim()
        if (text.isEmpty()) {
            toast(context, "说点什么吧")
            return
        }
        ws.sending = true
        // 用根级 scope：发送中切 tab / 点进主页也不会取消请求与结果处理。
        scope.launch {
            // 服务端契约仍是 content_html：纯文本必须转义 + 换行转 <br> 后再发。
            val result = App.api.worldSend(RichHtml.fromPlainText(text))
            ws.sending = false
            if (result.ok) {
                // 发送期间用户可能已继续编辑：只清空仍等于本次发送内容的草稿。
                if (ws.draft.trim() == text) ws.draft = ""
                toast(context, "已发送")
                load(silent = true, toBottom = true)
            } else {
                toast(context, result.message)
            }
        }
    }

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
                Text("世界频道", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                Text(
                    text = "最近 ${Constants.WORLD_LIMIT} 条 · 每 20 秒自动刷新",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                )
            }
            IconButton(onClick = { scope.launch { load() } }) {
                Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = colors.textPrimary)
            }
        }

        // 列表区占满剩余高度：否则「加载中 / 空 / 错误」占位时输入行会浮到页面中间。
        Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
            when {
                loading && messages.isEmpty() -> LoadingBox()
                error.isNotBlank() && messages.isEmpty() -> ErrorBox(error, onRetry = { scope.launch { load() } })
                messages.isEmpty() -> EmptyBox("世界频道暂无消息")
                else -> LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(items = messages, key = { it.id }) { m ->
                        WorldBubble(
                            message = m,
                            mine = meId.isNotBlank() && m.senderId == meId,
                            onUser = { if (m.senderId.isNotBlank()) nav.push(Screen.UserProfile(m.senderId)) },
                        )
                    }
                }
            }
        }

        // 底部直接内联纯文本输入框（不支持富文本，也不再打开全屏编辑器）。
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.bgHeader)
                .imePadding()
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            if (App.isLoggedIn) {
                ForumTextField(
                    value = ws.draft,
                    onValueChange = { ws.draft = takeCodePoints(it, WORLD_TEXT_MAX_CHARS) },
                    placeholder = "说点什么…",
                    singleLine = false,
                    maxLines = 4,
                    minHeight = 44.dp,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                PrimaryButton(
                    text = if (ws.sending) "发送中…" else "发送",
                    enabled = ws.draft.isNotBlank() && !ws.sending,
                    onClick = { send() },
                )
            } else {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(10.dp))
                        .background(colors.bgInput)
                        .clickable {
                            toast(context, "请先登录")
                            nav.push(Screen.Auth())
                        }
                        .padding(horizontal = 12.dp, vertical = 11.dp),
                ) {
                    Text("登录后参与聊天", color = colors.textMuted, fontSize = 14.sp, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun WorldBubble(
    message: WorldMessage,
    mine: Boolean,
    onUser: () -> Unit,
) {
    val colors = ForumTheme.colors
    Row(modifier = Modifier.fillMaxWidth()) {
        Avatar(message.senderAvatar, 32.dp, onClick = onUser)
        Spacer(Modifier.width(8.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .clip(RoundedCornerShape(10.dp))
                .background(colors.bgCard)
                .padding(10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = message.senderName,
                    color = if (mine) colors.primary else colors.textAccent,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                )
                Spacer(Modifier.weight(1f))
                Text(TimeFmt.fmtTime(message.createdAt), color = colors.textMuted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(4.dp))
            // 世界频道正文是 HTML（也兼容历史 markdown），统一按 content_format 渲染。
            val doc = remember(message.id, message.content, message.contentFormat) {
                RichDocument.fromContent(message.content, message.contentFormat)
            }
            RichTextView(doc = doc, compact = true)
        }
    }
}
