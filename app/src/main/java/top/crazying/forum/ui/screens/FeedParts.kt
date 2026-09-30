package top.crazying.forum.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import top.crazying.forum.data.Post
import top.crazying.forum.ui.components.EmptyBox
import top.crazying.forum.ui.components.ErrorBox
import top.crazying.forum.ui.components.GhostButton
import top.crazying.forum.ui.components.LoadingBox
import top.crazying.forum.ui.components.PostCardView

/**
 * 帖子信息流列表（首页 / 论坛 / 搜索 / 个人主页共用）。
 *
 * 分页采用「尾部按钮 + 手动加载更多」而不是自动触发，
 * 避免滚动到底反复触发请求把服务端打爆。
 */
@Composable
fun PostFeedList(
    posts: List<Post>,
    loading: Boolean,
    error: String,
    hasMore: Boolean,
    onRetry: () -> Unit,
    onLoadMore: () -> Unit,
    onClickPost: (String) -> Unit,
    onClickUser: (String) -> Unit,
    modifier: Modifier = Modifier,
    emptyText: String = "暂无帖子",
    contentPadding: PaddingValues = PaddingValues(12.dp),
) {
    if (loading && posts.isEmpty()) {
        LoadingBox(modifier = modifier)
        return
    }
    if (error.isNotBlank() && posts.isEmpty()) {
        ErrorBox(message = error, onRetry = onRetry, modifier = modifier)
        return
    }
    if (posts.isEmpty()) {
        EmptyBox(text = emptyText, modifier = modifier)
        return
    }

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(items = posts, key = { it.id.ifBlank { it.title + it.createdAt } }) { post ->
            PostCardView(
                post = post,
                onClick = { onClickPost(post.id) },
                onUserClick = onClickUser,
            )
        }
        item {
            if (hasMore) {
                GhostButton(
                    text = if (loading) "加载中…" else "加载更多",
                    onClick = { if (!loading) onLoadMore() },
                    enabled = !loading,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                )
            } else {
                EmptyBox(text = "—— 到底了 ——")
            }
        }
    }
}
