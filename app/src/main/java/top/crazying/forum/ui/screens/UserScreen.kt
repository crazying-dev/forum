package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.style.TextOverflow
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
fun UserScreen(nav: Navigator, store: FeedStateStore, userId: String) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // 状态由根节点持有：从帖子详情返回时复用资料与列表，滚动位置不丢
    val st = remember(userId) { store.user(userId) }

    suspend fun loadProfile() {
        st.profileLoading = true
        val result = App.api.userInfo(userId)
        st.profileLoading = false
        if (!result.ok) {
            st.profileError = result.message
            return
        }
        st.profileError = ""
        st.user = result.jsonObj("user")?.let { UserItem.from(it) }
    }

    suspend fun loadList() {
        st.loading = true
        st.error = ""
        when (st.tab) {
            "comments" -> {
                val r = App.api.userComments(userId)
                if (r.ok) st.comments = CommentItem.list(r.rowsAny("comments", "replies"))
                else st.error = r.message
            }
            "favorites" -> {
                val r = App.api.userFavorites(userId)
                if (r.ok) st.posts = Post.list(r.rows("posts"))
                else st.error = r.message
            }
            else -> {
                val r = App.api.userPosts(userId)
                if (r.ok) {
                    val owner = st.user
                    st.posts = Post.list(r.rows("posts")).map {
                        if (owner != null) it.withAuthor(owner.id, owner.name, owner.avatar) else it
                    }
                } else st.error = r.message
            }
        }
        st.loading = false
    }

    // 首次进入（或切换用户）时加载资料；返回时 profileLoaded 已为 true，直接复用
    LaunchedEffect(userId) {
        if (!st.profileLoaded) {
            st.profileLoaded = true
            loadProfile()
        }
    }

    // tab 切换时才重建列表；从帖子详情返回时 loadedTab 未变 → 不重载，保留滚动位置
    LaunchedEffect(st.tab, st.user != null) {
        if (st.user != null && needReload(st.loadedTab, st.tab)) {
            st.posts = emptyList()
            st.comments = emptyList()
            st.loadedTab = st.tab
            loadList()
        }
    }

    val isSelf = App.isLoggedIn && App.userId == userId

    PageScaffold(title = st.user?.name ?: "用户主页", onBack = { nav.pop() }) { padding ->
        when {
            st.profileLoading && st.user == null -> Box(Modifier.fillMaxSize().padding(padding)) { LoadingBox() }
            st.user == null -> Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(st.profileError.ifBlank { "用户不存在" }, onRetry = { scope.launch { loadProfile() } })
            }
            else -> LazyColumn(
                state = st.listState,
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                val u = st.user!!
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
                        Pill("帖子", active = st.tab == "posts") { st.tab = "posts" }
                        Pill("收藏", active = st.tab == "favorites") { st.tab = "favorites" }
                        Pill("评论", active = st.tab == "comments") { st.tab = "comments" }
                    }
                }

                when {
                    st.loading -> item(key = "ll") { LoadingBox() }
                    st.error.isNotBlank() -> item(key = "le") {
                        ErrorBox(st.error, onRetry = { scope.launch { loadList() } })
                    }
                    st.tab == "comments" -> {
                        if (st.comments.isEmpty()) {
                            item(key = "ce") { EmptyBox("暂无评论") }
                        }
                        items(items = st.comments, key = { "c" + it.id }) { c ->
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(colors.bgCard)
                                    .clickable(enabled = c.postId.isNotBlank()) {
                                        nav.push(Screen.PostDetail(c.postId))
                                    }
                                    .padding(12.dp),
                            ) {
                                // 该评论所属帖子：点击整行可进入对应帖子详情。
                                Text(
                                    text = "评论于 " + c.postTitle.ifBlank { "帖子 " + c.postId },
                                    color = colors.textAccent,
                                    fontSize = 12.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Spacer(Modifier.height(4.dp))
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
                    st.posts.isEmpty() -> item(key = "pe") { EmptyBox("暂无内容") }
                    else -> items(items = st.posts, key = { "p" + it.id }) { p ->
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
