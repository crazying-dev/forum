package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.data.CommentItem
import top.crazying.forum.data.Post
import top.crazying.forum.data.UserItem
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

/** 其他用户的主页：资料卡 + 关注 + 帖子/收藏/评论 三个列表。 */
@Composable
fun UserScreen(nav: Navigator, userId: String) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var user by remember { mutableStateOf<UserItem?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf("posts") }
    var posts by remember { mutableStateOf<List<Post>>(emptyList()) }
    var comments by remember { mutableStateOf<List<CommentItem>>(emptyList()) }
    var listLoading by remember { mutableStateOf(false) }
    var listError by remember { mutableStateOf("") }

    suspend fun loadProfile() {
        loading = true
        val result = App.api.userInfo(userId)
        loading = false
        if (!result.ok) {
            error = result.message
            return
        }
        error = ""
        user = result.jsonObj("user")?.let { UserItem.from(it) }
    }

    suspend fun loadList() {
        listLoading = true
        listError = ""
        when (tab) {
            "comments" -> {
                val r = App.api.userComments(userId)
                if (r.ok) comments = CommentItem.list(r.rowsAny("comments", "replies"))
                else listError = r.message
            }
            "favorites" -> {
                val r = App.api.userFavorites(userId)
                if (r.ok) posts = Post.list(r.rows("posts"))
                else listError = r.message
            }
            else -> {
                val r = App.api.userPosts(userId)
                if (r.ok) {
                    val owner = user
                    posts = Post.list(r.rows("posts")).map {
                        if (owner != null) it.withAuthor(owner.id, owner.name, owner.avatar) else it
                    }
                } else listError = r.message
            }
        }
        listLoading = false
    }

    LaunchedEffect(userId) {
        loadProfile()
        tab = "posts"
        posts = emptyList()
        comments = emptyList()
        loadList()
    }

    LaunchedEffect(tab) {
        if (user != null) {
            posts = emptyList()
            comments = emptyList()
            loadList()
        }
    }

    val isSelf = App.isLoggedIn && App.userId == userId

    PageScaffold(title = user?.name ?: "用户主页", onBack = { nav.pop() }) { padding ->
        when {
            loading && user == null -> Box(Modifier.fillMaxSize().padding(padding)) { LoadingBox() }
            user == null -> Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(error.ifBlank { "用户不存在" }, onRetry = { scope.launch { loadProfile() } })
            }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                val u = user!!
                item(key = "card") {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(colors.bgCard)
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Avatar(u.avatar, 58.dp)
                            Spacer(Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(u.name, color = colors.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                                if (u.title.isNotBlank()) {
                                    Spacer(Modifier.height(4.dp))
                                    Pill(u.title)
                                }
                            }
                            if (!isSelf) {
                                GhostButton(
                                    text = if (u.isFollowing) "已关注" else "关注",
                                    tint = if (u.isFollowing) colors.textMuted else colors.primary,
                                    onClick = {
                                        if (!App.isLoggedIn) {
                                            toast(context, "请先登录")
                                            nav.push(Screen.Auth())
                                        } else {
                                            scope.launch {
                                                val r = App.api.follow(userId)
                                                if (r.ok) {
                                                    toast(context, "已关注")
                                                    loadProfile()
                                                } else toast(context, r.message)
                                            }
                                        }
                                    },
                                )
                            }
                        }

                        val metaParts = mutableListOf<String>()
                        metaParts.add("性别 " + u.genderText)
                        if (u.birthdayText.isNotBlank()) metaParts.add("生日 " + u.birthdayText)
                        if (u.ageText.isNotBlank()) metaParts.add(u.ageText + " 岁")
                        Text(metaParts.joinToString("   "), color = colors.textMuted, fontSize = 12.sp)

                        Text(
                            text = "帖子 ${u.postCount}   获赞 ${u.totalLikes}   浏览 ${u.totalViews}   关注 ${u.followingCount}   粉丝 ${u.followerCount}",
                            color = colors.textSecondary,
                            fontSize = 12.sp,
                        )

                        if (u.intro.isNotBlank()) {
                            Text(u.intro, color = colors.textPrimary, fontSize = 13.sp)
                        }
                        if (u.createdAt.isNotBlank()) {
                            Text("注册于 " + TimeFmt.fmtTime(u.createdAt), color = colors.textMuted, fontSize = 12.sp)
                        }
                        if (isSelf && u.email.isNotBlank()) {
                            Text("邮箱 " + u.email, color = colors.textMuted, fontSize = 12.sp)
                        }
                    }
                }

                item(key = "tabs") {
                    Row(
                        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Pill("帖子", active = tab == "posts") { tab = "posts" }
                        Pill("收藏", active = tab == "favorites") { tab = "favorites" }
                        Pill("评论", active = tab == "comments") { tab = "comments" }
                    }
                }

                when {
                    listLoading -> item(key = "ll") { LoadingBox() }
                    listError.isNotBlank() -> item(key = "le") {
                        ErrorBox(listError, onRetry = { scope.launch { loadList() } })
                    }
                    tab == "comments" -> {
                        if (comments.isEmpty()) {
                            item(key = "ce") { EmptyBox("暂无评论") }
                        }
                        items(items = comments, key = { "c" + it.id }) { c ->
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(colors.bgCard)
                                    .padding(12.dp),
                            ) {
                                Text(c.content, color = colors.textPrimary, fontSize = 14.sp)
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    TimeFmt.fmtTime(c.createdAt),
                                    color = colors.textMuted,
                                    fontSize = 11.sp,
                                )
                            }
                        }
                    }
                    posts.isEmpty() -> item(key = "pe") { EmptyBox("暂无内容") }
                    else -> items(items = posts, key = { "p" + it.id }) { p ->
                        PostCardView(
                            post = p,
                            onClick = { nav.push(Screen.PostDetail(p.id)) },
                            onUserClick = { uid -> if (uid.isNotBlank()) nav.push(Screen.UserProfile(uid)) },
                        )
                    }
                }
            }
        }
    }
}
