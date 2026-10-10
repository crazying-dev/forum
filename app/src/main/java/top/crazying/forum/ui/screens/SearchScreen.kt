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
fun SearchScreen(nav: Navigator, store: FeedStateStore, initialKeyword: String = "") {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    // 状态由根节点持有：从帖子详情返回时复用（关键词 / 结果 / 滚动位置都不丢）
    val st = remember { store.search(initialKeyword) }

    suspend fun runSearch() {
        val k = st.keyword.trim()
        if (k.length < 2) {
            st.error = "请输入至少 2 个字符"
            return
        }
        st.loading = true
        st.error = ""
        val result = App.api.search(k, page = 1, pageSize = Constants.PAGE_SIZE, type = st.type)
        st.loading = false
        st.searched = true
        if (!result.ok) {
            st.error = result.message
            st.posts = emptyList()
            st.users = emptyList()
            return
        }
        st.posts = Post.list(result.rows("posts"))
        st.users = UserItem.list(result.rows("users"))
    }

    // 带关键词进入时自动搜索一次；从帖子详情返回时 st.searched 已为 true，不重复搜索
    LaunchedEffect(Unit) {
        if (!st.searched && initialKeyword.trim().length >= 2) runSearch()
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
                        value = st.keyword,
                        onValueChange = { st.keyword = it },
                        placeholder = "搜索帖子 / 用户",
                        modifier = Modifier.weight(1f),
                    )
                    PrimaryButton(text = "搜索", onClick = { scope.launch { runSearch() } })
                }
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Pill(text = "全部", active = st.type == "both") { st.type = "both" }
                    Pill(text = "帖子", active = st.type == "posts") { st.type = "posts" }
                    Pill(text = "用户", active = st.type == "users") { st.type = "users" }
                }
            }

            when {
                st.loading -> LoadingBox()
                st.error.isNotBlank() -> ErrorBox(message = st.error, onRetry = { scope.launch { runSearch() } })
                !st.searched -> EmptyBox("输入关键词后点击搜索")
                st.posts.isEmpty() && st.users.isEmpty() -> EmptyBox("没有找到相关内容")
                else -> LazyColumn(
                    state = st.listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (st.users.isNotEmpty()) {
                        item(key = "ut") { SectionTitle("用户（${st.users.size}）") }
                        items(items = st.users, key = { "u" + it.id }) { u ->
                            UserRow(
                                name = u.name,
                                avatar = u.avatar,
                                subtitle = if (u.intro.isNotBlank()) u.intro else "帖子 ${u.postCount} · 粉丝 ${u.followerCount}",
                                onClick = { nav.push(Screen.UserProfile(u.id)) },
                            )
                        }
                    }
                    if (st.posts.isNotEmpty()) {
                        item(key = "pt") { SectionTitle("帖子（${st.posts.size}）") }
                        items(items = st.posts, key = { "p" + it.id }) { p ->
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
