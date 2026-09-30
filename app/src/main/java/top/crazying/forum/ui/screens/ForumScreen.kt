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
fun ForumScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    // "" 代表「全部」
    var category by remember { mutableStateOf("") }
    var posts by remember { mutableStateOf<List<Post>>(emptyList()) }
    var page by remember { mutableStateOf(1) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var hasMore by remember { mutableStateOf(false) }

    suspend fun load(targetPage: Int, replace: Boolean) {
        loading = true
        if (replace) error = ""
        val cat = category
        val result = App.api.posts(
            page = targetPage,
            pageSize = Constants.PAGE_SIZE,
            category = cat.ifBlank { null },
        )
        if (cat != category) return
        loading = false
        if (!result.ok) {
            error = result.message
            return
        }
        val list = Post.list(result.rows("posts"))
        posts = if (replace) list else posts + list
        page = targetPage
        hasMore = list.size >= Constants.PAGE_SIZE
    }

    LaunchedEffect(category) {
        posts = emptyList()
        page = 1
        hasMore = false
        load(1, true)
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
            IconButton(onClick = { nav.push(Screen.PostCreate(category.ifBlank { "general" })) }) {
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
            Pill(text = "全部", active = category.isBlank()) { category = "" }
            for (key in Constants.CATEGORY_ORDER) {
                Pill(
                    text = Constants.categoryLabel(key),
                    active = category == key,
                    onClick = { category = key },
                )
            }
        }

        PostFeedList(
            posts = posts,
            loading = loading,
            error = error,
            hasMore = hasMore,
            onRetry = { scope.launch { load(1, true) } },
            onLoadMore = { scope.launch { load(page + 1, false) } },
            onClickPost = { id -> if (id.isNotBlank()) nav.push(Screen.PostDetail(id)) },
            onClickUser = { uid -> if (uid.isNotBlank()) nav.push(Screen.UserProfile(uid)) },
        )
    }
}
