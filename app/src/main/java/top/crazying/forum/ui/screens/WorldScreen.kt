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
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.core.WorldFeed
import top.crazying.forum.data.WorldMessage
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

/**
 * 世界频道。
 *
 * 本轮用「拉取 `/api/world/ALL` + 20 秒轮询」而不是 WebSocket，
 * 好处是不必引入长连接与重连状态机，代价是消息有最多 20 秒延迟（已在 README 标注）。
 */
@Composable
fun WorldScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val meId = App.userId
    val listState = rememberLazyListState()

    var messages by remember { mutableStateOf<List<WorldMessage>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    /** 需要在下一帧把列表滚到底（首次加载 / 刚发完消息）。 */
    var pendingScrollToBottom by remember { mutableStateOf(false) }

    // 列表更新后再滚动：此时 LazyColumn 已经拿到新数据，scrollToItem 才生效。
    LaunchedEffect(messages) {
        if (pendingScrollToBottom && messages.isNotEmpty()) {
            pendingScrollToBottom = false
            runCatching { listState.scrollToItem(messages.lastIndex) }
        }
    }

    suspend fun load(silent: Boolean = false, toBottom: Boolean = false) {
        if (!silent) loading = true
        val result = App.api.worldAll()
        if (!silent) loading = false
        if (!result.ok) {
            if (!silent) error = result.message
            return
        }
        error = ""
        val list = WorldMessage.list(result.rows(null))
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

    fun send() {
        val text = input.trim()
        if (text.isEmpty() || sending) return
        if (!App.isLoggedIn) {
            toast(context, "请先登录")
            nav.push(Screen.Auth())
            return
        }
        sending = true
        scope.launch {
            val result = App.api.worldSend(text)
            sending = false
            if (result.ok) {
                input = ""
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

        when {
            loading && messages.isEmpty() -> LoadingBox()
            error.isNotBlank() && messages.isEmpty() -> ErrorBox(error, onRetry = { scope.launch { load() } })
            messages.isEmpty() -> EmptyBox("世界频道暂无消息")
            else -> LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f),
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

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.bgHeader)
                .navigationBarsPadding()
                .imePadding()
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ForumTextField(
                value = input,
                onValueChange = { if (it.length <= 500) input = it },
                placeholder = "说点什么…（不超过 500 字）",
                modifier = Modifier.weight(1f),
            )
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (sending) colors.bgItemActive else colors.primary)
                    .clickable(enabled = !sending) { send() }
                    .padding(11.dp),
            ) {
                Icon(Icons.Default.Send, contentDescription = "发送", tint = colors.primaryText)
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
            Text(message.content, color = colors.textPrimary, fontSize = 14.sp)
        }
    }
}
