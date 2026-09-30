package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.data.Post
import top.crazying.forum.data.UserItem
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

/** 搜索：帖子 + 用户（服务端要求关键词至少 2 个字符）。 */
@Composable
fun SearchScreen(nav: Navigator, initialKeyword: String = "") {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    var keyword by remember { mutableStateOf(initialKeyword) }
    var type by remember { mutableStateOf("both") }
    var posts by remember { mutableStateOf<List<Post>>(emptyList()) }
    var users by remember { mutableStateOf<List<UserItem>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var searched by remember { mutableStateOf(false) }

    suspend fun runSearch() {
        val k = keyword.trim()
        if (k.length < 2) {
            error = "请输入至少 2 个字符"
            return
        }
        loading = true
        error = ""
        val result = App.api.search(k, page = 1, pageSize = Constants.PAGE_SIZE, type = type)
        loading = false
        searched = true
        if (!result.ok) {
            error = result.message
            posts = emptyList()
            users = emptyList()
            return
        }
        posts = Post.list(result.rows("posts"))
        users = UserItem.list(result.rows("users"))
    }

    LaunchedEffect(Unit) {
        if (initialKeyword.trim().length >= 2) runSearch()
    }

    PageScaffold(title = "搜索", onBack = { nav.pop() }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(colors.bgBody),
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    ForumTextField(
                        value = keyword,
                        onValueChange = { keyword = it },
                        placeholder = "搜索帖子 / 用户",
                        modifier = Modifier.weight(1f),
                    )
                    PrimaryButton(text = "搜索", onClick = { scope.launch { runSearch() } })
                }
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Pill(text = "全部", active = type == "both") { type = "both" }
                    Pill(text = "帖子", active = type == "posts") { type = "posts" }
                    Pill(text = "用户", active = type == "users") { type = "users" }
                }
            }

            when {
                loading -> LoadingBox()
                error.isNotBlank() -> ErrorBox(message = error, onRetry = { scope.launch { runSearch() } })
                !searched -> EmptyBox("输入关键词后点击搜索")
                posts.isEmpty() && users.isEmpty() -> EmptyBox("没有找到相关内容")
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (users.isNotEmpty()) {
                        item(key = "ut") { SectionTitle("用户（${users.size}）") }
                        items(items = users, key = { "u" + it.id }) { u ->
                            UserRow(
                                name = u.name,
                                avatar = u.avatar,
                                subtitle = if (u.intro.isNotBlank()) u.intro else "帖子 ${u.postCount} · 粉丝 ${u.followerCount}",
                                onClick = { nav.push(Screen.UserProfile(u.id)) },
                            )
                        }
                    }
                    if (posts.isNotEmpty()) {
                        item(key = "pt") { SectionTitle("帖子（${posts.size}）") }
                        items(items = posts, key = { "p" + it.id }) { p ->
                            PostCardView(
                                post = p,
                                onClick = { nav.push(Screen.PostDetail(p.id)) },
                                onUserClick = { uid -> if (uid.isNotBlank()) nav.push(Screen.UserProfile(uid)) },
                            )
                        }
                    }
                    item { EmptyBox("—— 到底了 ——") }
                }
            }
        }
    }
}
