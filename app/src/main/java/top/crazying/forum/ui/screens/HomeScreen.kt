package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.data.Post
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.Avatar
import top.crazying.forum.ui.components.GhostButton
import top.crazying.forum.ui.components.Pill

/** 首页：欢迎语 + 多个信息流（最新发布 / 综合排序 / 随机推荐 / 我的收藏）。 */
@Composable
fun HomeScreen(nav: Navigator, store: FeedStateStore) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()
    val me = App.user.value
    val name = me?.optString("name", "") ?: ""
    val avatar = me?.optString("avatar", "") ?: ""
    val meId = me?.optString("id", "") ?: ""

    // 状态由根节点持有：从帖子详情返回时复用，列表内容与滚动位置都不丢
    val st = remember { store.feed("home", "latest") }

    suspend fun load(targetPage: Int, replace: Boolean) {
        st.loading = true
        if (replace) st.error = ""
        val kind = st.filter
        val result = when (kind) {
            "random" -> App.api.randomPosts(Constants.RANDOM_LIMIT)
            "comprehensive" -> App.api.posts(
                page = 1,
                pageSize = Constants.COMPREHENSIVE_LIMIT,
                sort = "comprehensive",
            )
            "favorites" -> App.api.userFavorites(
                userId = App.userId,
                page = targetPage,
                pageSize = Constants.PAGE_SIZE,
            )
            else -> App.api.posts(
                page = targetPage,
                pageSize = Constants.PAGE_SIZE,
                sort = "time",
            )
        }
        if (st.filter != kind) return
        st.loading = false
        if (!result.ok) {
            st.error = result.message
            return
        }
        val list = Post.list(result.rows("posts"))
        st.posts = if (replace) list else st.posts + list
        st.page = targetPage
        st.hasMore = kind == "latest" && list.size >= Constants.PAGE_SIZE
    }

    // 内容标识（信息流 + 登录用户）不变时不重载：
    // 从帖子详情返回时标识照旧，直接复用已加载数据与滚动位置
    val contentKey = st.filter + "|" + meId
    LaunchedEffect(contentKey) {
        if (needReload(st.loadedKey, contentKey)) {
            st.posts = emptyList()
            st.page = 1
            st.hasMore = false
            st.loadedKey = contentKey
            load(1, true)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 12.dp, top = 10.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = if (name.isNotBlank()) "欢迎回来，$name" else "妖精论坛",
                    color = colors.textPrimary,
                    fontSize = 19.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                )
                Text(
                    text = if (name.isNotBlank()) "切换上方信息流，点击帖子查看详情" else "登录后可收藏与关注",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                    maxLines = 1,
                )
            }
            IconButton(onClick = { nav.push(Screen.Search()) }) {
                Icon(Icons.Default.Search, contentDescription = "搜索", tint = colors.textPrimary)
            }
            IconButton(onClick = { nav.push(Screen.PostCreate()) }) {
                Icon(Icons.Default.Add, contentDescription = "发帖", tint = colors.textPrimary)
            }
            if (name.isBlank()) {
                GhostButton(text = "登录", onClick = { nav.push(Screen.Auth()) })
            } else {
                Avatar(avatar, 34.dp, onClick = { nav.push(Screen.Me) })
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FeedChip("最新发布", st.filter == "latest") {
                if (st.filter != "latest") st.filter = "latest" else scope.launch { load(1, true) }
            }
            FeedChip("综合排序", st.filter == "comprehensive") { st.filter = "comprehensive" }
            FeedChip("随机推荐", st.filter == "random") { st.filter = "random" }
            if (name.isNotBlank()) {
                FeedChip("我的收藏", st.filter == "favorites") { st.filter = "favorites" }
            }
        }

        PostFeedList(
            posts = st.posts,
            loading = st.loading,
            error = st.error,
            hasMore = st.hasMore,
            onRetry = { scope.launch { load(1, true) } },
            onLoadMore = { scope.launch { load(st.page + 1, false) } },
            onClickPost = { id -> if (id.isNotBlank()) nav.push(Screen.PostDetail(id)) },
            onClickUser = { uid -> if (uid.isNotBlank()) nav.push(Screen.UserProfile(uid)) },
            emptyText = if (st.filter == "favorites") "还没有收藏的帖子" else "暂无帖子",
            state = st.listState,
        )
    }

    // 收藏流需要登录态，掉线时自动退回最新发布
    LaunchedEffect(me) {
        if (me == null && st.filter == "favorites") st.filter = "latest"
    }
}

@Composable
private fun FeedChip(text: String, active: Boolean, onClick: () -> Unit) {
    Pill(text = text, active = active, onClick = onClick)
}
