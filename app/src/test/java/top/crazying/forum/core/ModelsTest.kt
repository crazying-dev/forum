package top.crazying.forum.core

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import top.crazying.forum.data.CommentItem
import top.crazying.forum.data.Post
import top.crazying.forum.data.UserItem
import top.crazying.forum.data.WorldMessage

/**
 * 数据模型 JSON 映射用例（Post / CommentItem / WorldMessage / UserItem）。
 *
 * 字段名对齐 ouo `/ov2/api`：正文格式是 `content_format`，点赞态是 `liked_by_me`，
 * 世界频道用 `sender_*`，用户资料统计在 `stats` / `follow_stats`。
 */
class ModelsTest {

    @Test
    fun post_parsesHtmlContentFormat() {
        val post = Post.from(
            JSONObject()
                .put("id", "p-1")
                .put("title", "标题")
                .put("summary", "摘要")
                .put("content", "<p>正文</p>")
                .put("content_format", "html")
                .put("category", "tech")
                .put("user_id", "u-1")
                .put("user_name", "小明")
                .put("likes", 5)
                .put("views", 12)
                .put("comment_count", 3)
                .put("created_at", "2026-01-02T03:04:05Z"),
        )

        assertEquals("html", post.contentFormat)
        assertEquals("p-1", post.id)
        assertEquals("<p>正文</p>", post.content)
        assertEquals(5, post.likes)
        assertEquals(3, post.commentCount)
    }

    @Test
    fun comment_parsesLikedByMe() {
        val comment = CommentItem.from(
            JSONObject()
                .put("id", "c-1")
                .put("content", "评论内容")
                .put("content_format", "html")
                .put("user_id", "u-2")
                .put("user_name", "小红")
                .put("likes", 2)
                .put("liked_by_me", true)
                .put("parent_id", "c-0")
                .put("post_id", "p-1"),
        )

        assertTrue(comment.liked)
        assertEquals("html", comment.contentFormat)
        assertEquals("c-0", comment.parentId)
        assertTrue(comment.isReply)
    }

    @Test
    fun worldMessage_parsesItemsEntry() {
        val payload = JSONObject().put(
            "items",
            JSONArray().put(
                JSONObject()
                    .put("id", "w-1")
                    .put("sender_id", "u-3")
                    .put("sender_name", "路人")
                    .put("sender_avatar", "https://example.com/a.png")
                    .put("content", "<p>你好</p>")
                    .put("content_format", "html")
                    .put("parent_id", 3)
                    .put("created_at", "2026-01-02T03:04:05Z"),
            ),
        )

        val array = payload.getJSONArray("items")
        val messages = WorldMessage.list((0 until array.length()).map { array.getJSONObject(it) })
        val message = messages.single()

        assertEquals("w-1", message.id)
        assertEquals("u-3", message.senderId)
        assertEquals("路人", message.senderName)
        assertEquals("https://example.com/a.png", message.senderAvatar)
        assertEquals("html", message.contentFormat)
        assertEquals("3", message.parentId)
        assertEquals("<p>你好</p>", message.content)
    }

    @Test
    fun userItem_fromProfile_readsStatsAndFollowState() {
        val user = JSONObject()
            .put("id", "u-4")
            .put("name", "阿黄")
            .put("avatar", "https://example.com/b.png")
            .put("prefix", "前辈")
            .put("intro", "简介")
        val stats = JSONObject()
            .put("post_count", 8)
            .put("total_likes", 40)
            .put("total_views", 200)
        val followStats = JSONObject()
            .put("following_count", 6)
            .put("follower_count", 9)

        val item = UserItem.fromProfile(
            user = user,
            stats = stats,
            followStats = followStats,
            isFollowing = true,
            isSelf = false,
        )

        assertEquals(8, item.postCount)
        assertEquals(6, item.followingCount)
        assertEquals(9, item.followerCount)
        assertTrue(item.isFollowing)
        assertFalse(item.isSelf)
        assertEquals("前辈", item.title)
    }

    @Test
    fun userItem_fromProfile_followsFallBackToStats() {
        val user = JSONObject().put("id", "u-5").put("name", "无名")
        val stats = JSONObject()
            .put("post_count", 1)
            .put("following_count", 2)
            .put("follower_count", 3)

        val item = UserItem.fromProfile(user, stats)

        assertEquals(1, item.postCount)
        assertEquals(2, item.followingCount)
        assertEquals(3, item.followerCount)
        assertFalse(item.isFollowing)
        assertFalse(item.isSelf)
    }
}
