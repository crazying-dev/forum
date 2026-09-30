package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.data.CommentItem
import top.crazying.forum.data.Post
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

/** 帖子详情：正文 + 点赞/收藏 + 评论列表 + 发评论。 */
@Composable
fun PostDetailScreen(nav: Navigator, postId: String) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val meId = App.userId

    var post by remember { mutableStateOf<Post?>(null) }
    var comments by remember { mutableStateOf<List<CommentItem>>(emptyList()) }
    var liked by remember { mutableStateOf(false) }
    var favorited by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    var input by remember { mutableStateOf("") }
    var replyTo by remember { mutableStateOf<CommentItem?>(null) }
    var sending by remember { mutableStateOf(false) }

    suspend fun load() {
        loading = true
        val result = App.api.getPost(postId)
        loading = false
        if (!result.ok) {
            error = result.message
            return
        }
        error = ""
        post = result.jsonObj("post")?.let { Post.from(it) }
        liked = result.bool("liked")
        favorited = result.bool("favorited")
        comments = CommentItem.list(result.rows("comments"))
    }

    LaunchedEffect(postId) { load() }

    fun requireLogin(): Boolean {
        if (App.isLoggedIn) return true
        toast(context, "请先登录")
        nav.push(Screen.Auth())
        return false
    }

    fun sendComment() {
        val text = input.trim()
        if (text.isEmpty() || sending) return
        if (!requireLogin()) return
        sending = true
        val parent = replyTo?.id
        scope.launch {
            val result = App.api.createComment(postId, text, parent)
            sending = false
            if (result.ok) {
                input = ""
                replyTo = null
                toast(context, "评论已发布")
                load()
            } else {
                toast(context, result.message)
            }
        }
    }

    PageScaffold(
        title = "帖子详情",
        onBack = { nav.pop() },
        actions = {
            IconButton(onClick = { scope.launch { load() } }) {
                Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = colors.textPrimary)
            }
        },
        bottomBar = {
            CommentComposer(
                value = input,
                onValueChange = { input = it },
                replyToName = replyTo?.userName,
                onCancelReply = { replyTo = null },
                sending = sending,
                onSend = { sendComment() },
            )
        },
    ) { padding ->
        when {
            loading && post == null -> Box(Modifier.fillMaxSize().padding(padding)) {
                LoadingBox()
            }

            post == null -> Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(
                    message = error.ifBlank { "帖子不存在或已被删除" },
                    onRetry = { scope.launch { load() } },
                )
            }

            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                val p = post!!
                item(key = "head") {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(colors.bgCard)
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Avatar(p.userAvatar, 38.dp) {
                                if (p.userId.isNotBlank()) nav.push(Screen.UserProfile(p.userId))
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = p.userName,
                                    color = colors.textAccent,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Medium,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.clickable(enabled = p.userId.isNotBlank()) {
                                        nav.push(Screen.UserProfile(p.userId))
                                    },
                                )
                                Text(
                                    text = "${p.categoryLabel} · ${TimeFmt.fmtTime(p.createdAt)}",
                                    color = colors.textMuted,
                                    fontSize = 12.sp,
                                )
                            }
                        }
                        Text(
                            text = p.title,
                            color = colors.textPrimary,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        HDivider()
                        if (p.content.isNotBlank()) {
                            HtmlBody(p.content)
                        }
                        HDivider()
                        Text(
                            text = "赞 ${p.likes} · 阅 ${p.views} · 评 ${p.commentCount} · ${TimeFmt.fmtDateTime(p.createdAt)}",
                            color = colors.textMuted,
                            fontSize = 12.sp,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            GhostButton(
                                text = if (liked) "已赞" else "点赞",
                                onClick = {
                                    if (!requireLogin()) return@GhostButton
                                    scope.launch {
                                        val r = App.api.likePost(postId)
                                        if (r.ok) {
                                            liked = true
                                            load()
                                        } else toast(context, r.message)
                                    }
                                },
                                tint = if (liked) colors.primary else null,
                            )
                            GhostButton(
                                text = if (favorited) "已收藏" else "收藏",
                                onClick = {
                                    if (!requireLogin()) return@GhostButton
                                    scope.launch {
                                        val r = App.api.favoritePost(postId)
                                        if (r.ok) {
                                            favorited = true
                                            load()
                                        } else toast(context, r.message)
                                    }
                                },
                                tint = if (favorited) colors.primary else null,
                            )
                        }
                    }
                }

                item(key = "ct") {
                    SectionTitle("评论（${comments.size}）")
                }

                if (comments.isEmpty()) {
                    item(key = "empty") { EmptyBox("还没有评论，快来抢沙发") }
                }

                items(items = comments, key = { it.id }) { c ->
                    CommentRow(
                        comment = c,
                        isMine = meId.isNotBlank() && c.userId == meId,
                        onUser = { if (c.userId.isNotBlank()) nav.push(Screen.UserProfile(c.userId)) },
                        onReply = {
                            if (requireLogin()) {
                                replyTo = c
                                toast(context, "正在回复 ${c.userName}")
                            }
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun CommentRow(
    comment: CommentItem,
    isMine: Boolean,
    onUser: () -> Unit,
    onReply: () -> Unit,
) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.bgCard)
            .padding(start = if (comment.isReply) 34.dp else 12.dp, end = 12.dp, top = 10.dp, bottom = 10.dp),
    ) {
        Avatar(comment.userAvatar, 30.dp, onClick = onUser)
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = comment.userName,
                    color = colors.textAccent,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    modifier = Modifier.clickable { onUser() },
                )
                if (isMine) {
                    Spacer(Modifier.width(6.dp))
                    Text("我", color = colors.primary, fontSize = 11.sp)
                }
                Spacer(Modifier.weight(1f))
                Text(TimeFmt.fmtTime(comment.createdAt), color = colors.textMuted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(4.dp))
            Text(
                text = comment.content,
                color = colors.textPrimary,
                fontSize = 14.sp,
            )
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("赞 ${comment.likes}", color = colors.textMuted, fontSize = 11.sp)
                Spacer(Modifier.width(14.dp))
                Text(
                    text = "回复",
                    color = colors.primary,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable { onReply() },
                )
            }
        }
    }
}

@Composable
private fun CommentComposer(
    value: String,
    onValueChange: (String) -> Unit,
    replyToName: String?,
    onCancelReply: () -> Unit,
    sending: Boolean,
    onSend: () -> Unit,
) {
    val colors = ForumTheme.colors
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.bgHeader)
            .navigationBarsPadding()
            .imePadding()
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (!replyToName.isNullOrBlank()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "正在回复 $replyToName",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = "取消",
                    color = colors.primary,
                    fontSize = 12.sp,
                    modifier = Modifier.clickable { onCancelReply() },
                )
            }
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ForumTextField(
                value = value,
                onValueChange = onValueChange,
                placeholder = "说点什么…（不超过 500 字）",
                modifier = Modifier.weight(1f),
            )
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (sending) colors.bgItemActive else colors.primary)
                    .clickable(enabled = !sending) { onSend() }
                    .padding(11.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "发送",
                    tint = colors.primaryText,
                )
            }
        }
    }
}
