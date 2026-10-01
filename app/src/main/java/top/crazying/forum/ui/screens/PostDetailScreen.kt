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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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

/**
 * 楼中楼扁平化后的一行：评论 + 层级深度 + 被回复人昵称。
 *
 * 只保留两层（0 = 根评论，1 = 其下所有回复）：对第 2 层的回复（孙级及更深）
 * 压平到第 2 层，并用 [replyToName]（直接父评论作者）显示「回复 @某人」；
 * 用「扁平列表 + depth 缩进」交给 [LazyColumn] 渲染，性能优于递归 Composable；
 * `key` 唯一稳定（优先取评论 id，极端空 id 才退化为位置键）。
 */
private data class CommentNode(
    val comment: CommentItem,
    val depth: Int,
    val replyToName: String?,
    val parent: CommentItem?,
    val key: String,
)

/**
 * 把扁平的评论列表按 `parentId` 组装成「父在前、子紧随其后」的扁平序列。
 *
 * 渲染只保留两层：根评论 + 其下所有回复（孙级及更深压平到第 2 层，
 * 由 [CommentNode.replyToName] 以「回复 @某人」标明实际回复对象）。
 *
 * - 根节点保持服务端返回顺序（时间序），子节点保持其在原列表中的相对顺序；
 * - `parentId` 在列表中找不到（孤儿）、或指向自身时按根节点处理，绝不丢评论；
 * - `visited` 集合防御自环 / 多父导致的无限递归与重复渲染。
 */
private fun buildCommentThread(comments: List<CommentItem>): List<CommentNode> {
    if (comments.isEmpty()) return emptyList()
    val byId = HashMap<String, CommentItem>(comments.size)
    for (c in comments) if (c.id.isNotBlank()) byId[c.id] = c

    val children = HashMap<String, MutableList<CommentItem>>()
    val roots = ArrayList<CommentItem>()
    for (c in comments) {
        val pid = c.parentId
        if (pid.isNotBlank() && pid != c.id && byId.containsKey(pid)) {
            children.getOrPut(pid) { ArrayList() }.add(c)
        } else {
            roots.add(c)
        }
    }

    val out = ArrayList<CommentNode>(comments.size)
    val visited = HashSet<String>()
    // depth 为真实层级；渲染只保留两层（0 = 根，1 = 其下所有回复）。
    fun emit(c: CommentItem, depth: Int, parent: CommentItem?) {
        if (c.id.isNotBlank() && !visited.add(c.id)) return
        out.add(
            CommentNode(
                comment = c,
                depth = if (depth == 0) 0 else 1,
                // 仅压平上来的回复（真实层级 >= 2）显示 @ 直接父评论作者
                replyToName = if (depth > 1) parent?.userName else null,
                parent = parent,
                key = c.id.ifBlank { "idx-${out.size}" },
            )
        )
        children[c.id]?.forEach { emit(it, depth + 1, c) }
    }
    for (r in roots) emit(r, 0, null)
    return out
}

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
    var pendingDeletePost by remember { mutableStateOf(false) }
    var pendingDeleteComment by remember { mutableStateOf<CommentItem?>(null) }
    var deleting by remember { mutableStateOf(false) }

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

    // 楼中楼：由扁平评论列表派生出带 depth 的渲染序列（不额外请求、不丢评论）。
    val nodes = remember(comments) { buildCommentThread(comments) }

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
                // 局部插入新评论，避免重新 getPost 让服务端浏览量 +1。
                val added = result.jsonObj("comment")?.let { CommentItem.from(it) }
                if (added != null) {
                    comments = comments + added
                    post = post?.let { p -> p.copy(commentCount = p.commentCount + 1) }
                } else {
                    // 极端情况下接口未回评论体，才兜底全量刷新（正常不会走到）。
                    load()
                }
                toast(context, "评论已发布")
            } else {
                toast(context, result.message)
            }
        }
    }

    fun deletePost() {
        val p = post ?: return
        if (deleting) return
        scope.launch {
            deleting = true
            val result = App.api.deletePost(p.id)
            deleting = false
            pendingDeletePost = false
            if (result.ok) {
                toast(context, "帖子已删除")
                // 返回上一页；列表页是独立组合，pop 后会重新进入并自动刷新。
                nav.pop()
            } else {
                toast(context, result.message)
            }
        }
    }

    fun deleteComment(target: CommentItem) {
        if (deleting) return
        scope.launch {
            deleting = true
            val result = App.api.deleteComment(target.id)
            deleting = false
            pendingDeleteComment = null
            if (result.ok) {
                // 本地移除该评论；其子评论若变孤儿，由 buildCommentThread 提升为根继续展示，不丢失。
                comments = comments.filterNot { it.id == target.id }
                post = post?.let { p ->
                    p.copy(commentCount = (p.commentCount - 1).coerceAtLeast(0))
                }
                toast(context, "评论已删除")
            } else {
                toast(context, result.message)
            }
        }
    }

    fun toggleCommentLike(target: CommentItem) {
        if (!requireLogin()) return
        scope.launch {
            val r = App.api.likeComment(target.id)
            if (r.ok) {
                // 用接口返回的 liked/likes 就地更新，绝不重新 getPost（否则浏览量 +1）。
                val newLiked = r.bool("liked", !target.liked)
                val newLikes = r.int("likes", target.likes)
                comments = comments.map {
                    if (it.id == target.id) it.copy(liked = newLiked, likes = newLikes) else it
                }
            } else {
                toast(context, r.message)
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
                                            // 用接口返回的 liked/likes 就地更新，绝不重新 getPost（否则浏览量 +1）。
                                            liked = r.bool("liked", !liked)
                                            post = post?.let { cur -> cur.copy(likes = r.int("likes", cur.likes)) }
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
                                            // 收藏接口只回 favorited，就地更新即可，不重新 getPost。
                                            favorited = r.bool("favorited", !favorited)
                                        } else toast(context, r.message)
                                    }
                                },
                                tint = if (favorited) colors.primary else null,
                            )
                            if (meId.isNotBlank() && p.userId == meId) {
                                GhostButton(
                                    text = if (deleting) "删除中…" else "删除",
                                    enabled = !deleting,
                                    tint = colors.danger,
                                    onClick = { pendingDeletePost = true },
                                )
                            }
                        }
                    }
                }

                item(key = "ct") {
                    SectionTitle("评论（${comments.size}）")
                }

                if (comments.isEmpty()) {
                    item(key = "empty") { EmptyBox("还没有评论，快来抢沙发") }
                }

                items(items = nodes, key = { it.key }) { node ->
                    val c = node.comment
                    CommentRow(
                        node = node,
                        isMine = meId.isNotBlank() && c.userId == meId,
                        onUser = { if (c.userId.isNotBlank()) nav.push(Screen.UserProfile(c.userId)) },
                        onReply = {
                            if (requireLogin()) {
                                replyTo = c
                                toast(context, "正在回复 ${c.userName}")
                            }
                        },
                        onReplyToParent = {
                            // 点击「回复 @昵称」：有父节点就回复父节点（不跳转，也不会崩）。
                            val parent = node.parent
                            if (parent != null && requireLogin()) {
                                replyTo = parent
                                toast(context, "正在回复 ${parent.userName}")
                            }
                        },
                        onDelete = { pendingDeleteComment = c },
                        onLike = { toggleCommentLike(c) },
                    )
                }
            }
        }

        if (pendingDeletePost) {
            AlertDialog(
                onDismissRequest = { if (!deleting) pendingDeletePost = false },
                title = { Text("删除帖子") },
                text = { Text("确定要删除这篇帖子吗？删除后不可恢复。") },
                confirmButton = {
                    TextButton(onClick = { deletePost() }, enabled = !deleting) {
                        Text(if (deleting) "删除中…" else "删除", color = colors.danger)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { pendingDeletePost = false }, enabled = !deleting) {
                        Text("取消")
                    }
                },
            )
        }

        val targetComment = pendingDeleteComment
        if (targetComment != null) {
            AlertDialog(
                onDismissRequest = { if (!deleting) pendingDeleteComment = null },
                title = { Text("删除评论") },
                text = { Text("确定要删除这条评论吗？删除后不可恢复。") },
                confirmButton = {
                    TextButton(onClick = { deleteComment(targetComment) }, enabled = !deleting) {
                        Text(if (deleting) "删除中…" else "删除", color = colors.danger)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { pendingDeleteComment = null }, enabled = !deleting) {
                        Text("取消")
                    }
                },
            )
        }
    }
}

@Composable
private fun CommentRow(
    node: CommentNode,
    isMine: Boolean,
    onUser: () -> Unit,
    onReply: () -> Unit,
    onReplyToParent: () -> Unit,
    onDelete: () -> Unit,
    onLike: () -> Unit,
) {
    val colors = ForumTheme.colors
    val comment = node.comment
    // 层级缩进：只保留两层（根 12dp / 回复 34dp）。
    val indent = (12 + node.depth.coerceAtMost(1) * 22).dp
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.bgCard)
            .padding(start = indent, end = 12.dp, top = 10.dp, bottom = 10.dp),
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
            val replyToName = node.replyToName
            if (!replyToName.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = "回复 @$replyToName",
                    color = colors.textAccent,
                    fontSize = 12.sp,
                    maxLines = 1,
                    modifier = Modifier.clickable { onReplyToParent() },
                )
            }
            Spacer(Modifier.height(4.dp))
            Text(
                text = comment.content,
                color = colors.textPrimary,
                fontSize = 14.sp,
            )
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = if (comment.liked) "已赞 ${comment.likes}" else "赞 ${comment.likes}",
                    color = if (comment.liked) colors.primary else colors.textMuted,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable { onLike() },
                )
                Spacer(Modifier.width(14.dp))
                Text(
                    text = "回复",
                    color = colors.primary,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable { onReply() },
                )
                if (isMine) {
                    Spacer(Modifier.width(14.dp))
                    Text(
                        text = "删除",
                        color = colors.danger,
                        fontSize = 11.sp,
                        modifier = Modifier.clickable { onDelete() },
                    )
                }
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
