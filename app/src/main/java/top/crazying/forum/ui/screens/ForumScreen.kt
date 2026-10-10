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
import top.crazying.forum.ui.components.Pill

/** 论坛页：按分类（综合/闲聊/求助/分享/创作）浏览帖子，支持分页。 */
@Composable
fun ForumScreen(nav: Navigator, store: FeedStateStore) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    // 状态由根节点持有：从帖子详情返回时复用，列表内容与滚动位置都不丢
    // filter 空串代表「全部」
    val st = remember { store.feed("forum") }

    suspend fun load(targetPage: Int, replace: Boolean) {
        st.loading = true
        if (replace) st.error = ""
        val cat = st.filter
        val result = App.api.posts(
            page = targetPage,
            pageSize = Constants.PAGE_SIZE,
            category = cat.ifBlank { null },
        )
        if (cat != st.filter) return
        st.loading = false
        if (!result.ok) {
            st.error = result.message
            return
        }
        val list = Post.list(result.rows("posts"))
        st.posts = if (replace) list else st.posts + list
        st.page = targetPage
        st.hasMore = list.size >= Constants.PAGE_SIZE
    }

    // 分类不变时不重载：从帖子详情返回时直接复用已加载数据与滚动位置
    LaunchedEffect(st.filter) {
        if (needReload(st.loadedKey, st.filter)) {
            st.posts = emptyList()
            st.page = 1
            st.hasMore = false
            st.loadedKey = st.filter
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
                    text = "论坛",
                    color = colors.textPrimary,
                    fontSize = 19.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "按分类浏览全部帖子",
                    color = colors.textMuted,
                    fontSize = 12.sp,
                )
            }
            IconButton(onClick = { nav.push(Screen.Search()) }) {
                Icon(Icons.Default.Search, contentDescription = "搜索", tint = colors.textPrimary)
            }
            IconButton(onClick = { nav.push(Screen.PostCreate(st.filter.ifBlank { "general" })) }) {
                Icon(Icons.Default.Add, contentDescription = "发帖", tint = colors.textPrimary)
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Pill(text = "全部", active = st.filter.isBlank()) { st.filter = "" }
            for (key in Constants.CATEGORY_ORDER) {
                Pill(
                    text = Constants.categoryLabel(key),
                    active = st.filter == key,
                    onClick = { st.filter = key },
                )
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
            state = st.listState,
        )
    }
}
