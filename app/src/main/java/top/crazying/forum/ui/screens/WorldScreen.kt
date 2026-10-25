package top.crazying.forum.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.ui.input.pointer.pointerInput
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
import top.crazying.forum.core.richtext.RichDocument
import top.crazying.forum.data.WorldMessage
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*
import top.crazying.forum.ui.richtext.RichTextEditorScreen
import top.crazying.forum.ui.richtext.RichTextView
import top.crazying.forum.ui.richtext.rememberRichEditorState

/** 世界频道图片上限：与服务端 `media.MaxInputBytes`（5MB）一致。 */
private const val WORLD_IMAGE_MAX_BYTES = 5 * 1024 * 1024

/** 从 MIME 推断扩展名（服务端只接受 jpeg / png / webp / gif）。 */
private fun worldImageExt(mime: String): String = when {
    mime.contains("png", ignoreCase = true) -> "png"
    mime.contains("webp", ignoreCase = true) -> "webp"
    mime.contains("gif", ignoreCase = true) -> "gif"
    else -> "jpg"
}

/**
 * 世界频道。
 *
 * 本轮用「拉取 `/api/world/messages` + 20 秒轮询」而不是 WebSocket，
 * 好处是不必引入长连接与重连状态机，代价是消息有最多 20 秒延迟（已在 README 标注）。
 * 消息正文是富文本 HTML，气泡内用 [RichTextView] 渲染；发送走全屏编辑器。
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
    /** 全屏发送器是否可见。 */
    var composing by remember { mutableStateOf(false) }
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

    /** 打开全屏发送器；未登录先去登录页。 */
    fun openComposer() {
        if (!App.isLoggedIn) {
            toast(context, "请先登录")
            nav.push(Screen.Auth())
            return
        }
        composing = true
    }

    Box(modifier = Modifier.fillMaxSize().background(colors.bgBody)) {
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

            // 底部只留一行「说点什么…」触发器，真正的编辑在覆盖式全屏编辑器里完成。
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(colors.bgHeader)
                    .navigationBarsPadding()
                    .imePadding()
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(10.dp))
                        .background(colors.bgInput)
                        .clickable { openComposer() }
                        .padding(horizontal = 12.dp, vertical = 11.dp),
                ) {
                    Text("说点什么…", color = colors.textMuted, fontSize = 14.sp, maxLines = 1)
                }
            }
        }

        if (composing) {
            // 背景带点击拦截：避免点击穿透到下面被覆盖的消息列表。
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(colors.bgBody)
                    .pointerInput(Unit) { detectTapGestures { } },
            ) {
                WorldComposer(
                    onCancel = { composing = false },
                    onSent = {
                        composing = false
                        scope.launch { load(silent = true, toBottom = true) }
                    },
                )
            }
        }
    }
}

/**
 * 世界频道发送器：全屏富文本编辑器，发送成功后由宿主刷新列表并滚到底。
 *
 * 每次打开都是全新的一次编辑（状态随组合销毁而丢弃）。
 */
@Composable
private fun WorldComposer(
    onCancel: () -> Unit,
    onSent: () -> Unit,
) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val editor = rememberRichEditorState()
    var sending by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }

    val pickImage = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = runCatching {
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            }.getOrNull()
            if (bytes == null) {
                toast(context, "读取图片失败")
                return@launch
            }
            if (bytes.size > WORLD_IMAGE_MAX_BYTES) {
                toast(context, "图片不能超过 5MB")
                return@launch
            }
            val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
            uploading = true
            val result = App.api.uploadImage(bytes, "image." + worldImageExt(mime), mime, "world_message")
            uploading = false
            if (result.ok) {
                val url = result.str("url")
                if (url.isNotBlank()) editor.insertImage(url) else toast(context, "上传成功但未返回图片地址")
            } else {
                toast(context, result.message)
            }
        }
    }

    fun send() {
        if (sending || uploading) return
        error = ""
        if (editor.toDocument().isBlank) {
            error = "说点什么吧"
            toast(context, error)
            return
        }
        sending = true
        scope.launch {
            val result = App.api.worldSend(editor.toHtml())
            sending = false
            if (result.ok) {
                toast(context, "已发送")
                onSent()
            } else {
                error = result.message
                toast(context, result.message)
            }
        }
    }

    RichTextEditorScreen(
        state = editor,
        title = "世界频道",
        publishLabel = "发送",
        publishing = sending,
        uploadingImage = uploading,
        placeholder = "说点什么…",
        overlay = true,
        header = {
            if (error.isNotBlank()) {
                Text(
                    text = error,
                    color = colors.danger,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                )
            }
        },
        onPickImage = { pickImage.launch("image/*") },
        onCancel = { if (!sending) onCancel() },
        onPublish = { send() },
    )
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
