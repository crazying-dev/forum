package top.crazying.forum.data

import org.json.JSONObject
import top.crazying.forum.core.Constants
import top.crazying.forum.core.TimeFmt

private fun JSONObject.s(key: String, def: String = ""): String {
    if (!has(key) || isNull(key)) return def
    return optString(key, def)
}

private fun JSONObject.i(key: String, def: Int = 0): Int {
    if (!has(key) || isNull(key)) return def
    return optInt(key, def)
}

private fun JSONObject.b(key: String, def: Boolean = false): Boolean {
    if (!has(key) || isNull(key)) return def
    return optBoolean(key, def)
}

/** 帖子（列表项 / 详情共用）。 */
data class Post(
    val id: String,
    val title: String,
    val summary: String,
    val content: String,
    val category: String,
    val userId: String,
    val userName: String,
    val userAvatar: String,
    val userTitle: String,
    val likes: Int,
    val views: Int,
    val commentCount: Int,
    val createdAt: String,
) {
    val categoryLabel: String get() = Constants.categoryLabel(category)

    /** 列表卡片优先用服务端 summary，没有就从正文 HTML 拓。 */
    val preview: String
        get() = summary.ifBlank { TimeFmt.stripHtml(content) }

    /** 补齐作者信息（部分接口不返回 user_* 字段）。 */
    fun withAuthor(userId: String = "", name: String = "", avatar: String = ""): Post {
        var p = this
        if (p.userId.isBlank() && userId.isNotBlank()) p = p.copy(userId = userId)
        if (p.userName.isBlank() && name.isNotBlank()) p = p.copy(userName = name)
        if (p.userAvatar.isBlank() && avatar.isNotBlank()) p = p.copy(userAvatar = avatar)
        return p
    }

    companion object {
        fun from(o: JSONObject): Post = Post(
            id = o.s("id"),
            title = o.s("title").ifBlank { "（无标题）" },
            summary = o.s("summary"),
            content = o.s("content"),
            category = o.s("category", "general"),
            userId = o.s("user_id"),
            userName = o.s("user_name").ifBlank { "匿名用户" },
            userAvatar = o.s("user_avatar"),
            userTitle = o.s("user_title"),
            likes = o.i("likes"),
            views = o.i("views"),
            commentCount = if (o.has("comments") && !o.isNull("comments")) o.i("comments")
            else o.i("comment_count"),
            createdAt = o.s("created_at"),
        )

        fun list(arr: List<JSONObject>): List<Post> = arr.map { from(it) }
    }
}

/** 评论（可能带 parent_id，支持一层回复）。 */
data class CommentItem(
    val id: String,
    val content: String,
    val userId: String,
    val userName: String,
    val userAvatar: String,
    val createdAt: String,
    val likes: Int,
    val liked: Boolean,
    val parentId: String,
) {
    val isReply: Boolean get() = parentId.isNotBlank()

    companion object {
        fun from(o: JSONObject): CommentItem = CommentItem(
            id = o.s("id"),
            content = o.s("content"),
            userId = o.s("user_id"),
            userName = o.s("user_name").ifBlank { "匿名用户" },
            userAvatar = o.s("user_avatar"),
            createdAt = o.s("created_at"),
            likes = o.i("likes"),
            liked = o.b("liked"),
            parentId = o.s("parent_id"),
        )

        fun list(arr: List<JSONObject>): List<CommentItem> = arr.map { from(it) }
    }
}

/** 用户公开资料 / 列表项。 */
data class UserItem(
    val id: String,
    val name: String,
    val avatar: String,
    val title: String,
    val gender: Int,
    val birthday: Any?,
    val intro: String,
    val email: String,
    val createdAt: String,
    val postCount: Int,
    val totalLikes: Int,
    val totalViews: Int,
    val followingCount: Int,
    val followerCount: Int,
    val isFollowing: Boolean,
    val isSelf: Boolean,
) {
    val birthdayText: String get() = TimeFmt.fmtBirthday(birthday)
    val ageText: String get() = TimeFmt.ageYears(birthday)

    val genderText: String
        get() = when (gender) {
            1 -> "男"
            2 -> "女"
            else -> "保密"
        }

    companion object {
        fun from(o: JSONObject): UserItem {
            val stats = o.optJSONObject("stats") ?: JSONObject()
            return UserItem(
                id = o.s("id"),
                name = o.s("name").ifBlank { "匿名用户" },
                avatar = o.s("avatar"),
                title = o.s("title"),
                gender = o.i("gender"),
                birthday = if (o.has("age") && !o.isNull("age")) o.opt("age") else null,
                intro = o.s("intro"),
                email = o.s("email"),
                createdAt = o.s("created_at"),
                postCount = stats.i("post_count"),
                totalLikes = stats.i("total_likes"),
                totalViews = stats.i("total_views"),
                followingCount = stats.i("following_count"),
                followerCount = stats.i("follower_count"),
                isFollowing = o.b("is_following"),
                isSelf = o.b("is_self"),
            )
        }

        fun list(arr: List<JSONObject>): List<UserItem> = arr.map { from(it) }
    }
}

/** 世界频道消息（字段名与帖子不同：sender_*）。 */
data class WorldMessage(
    val id: String,
    val senderId: String,
    val senderName: String,
    val senderAvatar: String,
    val content: String,
    val createdAt: String,
) {
    companion object {
        fun from(o: JSONObject): WorldMessage = WorldMessage(
            id = o.s("id"),
            senderId = o.s("sender_id"),
            senderName = o.s("sender_name").ifBlank { "匿名" },
            senderAvatar = o.s("sender_avatar"),
            content = o.s("content"),
            createdAt = o.s("created_at"),
        )

        fun list(arr: List<JSONObject>): List<WorldMessage> = arr.map { from(it) }
    }
}
