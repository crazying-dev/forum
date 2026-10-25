package top.crazying.forum.ui.richtext

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import top.crazying.forum.core.App
import top.crazying.forum.core.richtext.RichBlock

/** 引用卡片的展示数据（已归一化为用户/帖子/文章通用形态）。 */
data class EmbedData(
    val type: String,
    val id: String,
    val title: String,
    val subtitle: String,
    val avatar: String,
    val url: String,
)

/**
 * 引用卡片批量加载 + 内存缓存。
 *
 * 文档里可能同时出现多个 user/post/article 节点；按类型合并成三次批量请求
 * （`GET /ov2/api/embeds`），10 分钟内复用，最多缓存 200 条。
 */
object EmbedsStore {

    private data class Entry(val data: EmbedData, val at: Long)

    private const val TTL_MS = 10 * 60_000L
    private const val MAX_ENTRIES = 200

    private val mutex = Mutex()
    private val cache = LinkedHashMap<String, Entry>()

    fun key(type: String, id: String): String = type.trim().lowercase() + ":" + id.trim()

    suspend fun load(embeds: List<RichBlock.Embed>): Map<String, EmbedData> {
        if (embeds.isEmpty()) return emptyMap()
        val wanted = embeds
            .filter { it.id.isNotBlank() }
            .distinctBy { key(it.type, it.id) }
        if (wanted.isEmpty()) return emptyMap()

        mutex.withLock {
            val now = System.currentTimeMillis()
            val result = HashMap<String, EmbedData>()
            val missing = ArrayList<RichBlock.Embed>()
            for (e in wanted) {
                val k = key(e.type, e.id)
                val hit = cache[k]
                if (hit != null && now - hit.at <= TTL_MS) result[k] = hit.data else missing.add(e)
            }
            if (missing.isEmpty()) return result

            val users = missing.filter { it.type == "user" }.map { it.id }
            val posts = missing.filter { it.type == "post" }.map { it.id }
            val articles = missing.filter { it.type == "article" }.map { it.id }
            val res = runCatching { App.api.embeds(users, posts, articles) }.getOrNull()
            val obj = res?.takeIf { it.ok }?.obj()
            if (obj == null) return result

            parseUsers(obj).forEach { d -> result[key(d.type, d.id)] = d }
            parsePosts(obj).forEach { d -> result[key(d.type, d.id)] = d }
            parseArticles(obj).forEach { d -> result[key(d.type, d.id)] = d }

            for ((k, d) in result) {
                cache[k] = Entry(d, now)
            }
            while (cache.size > MAX_ENTRIES) {
                val first = cache.keys.firstOrNull() ?: break
                cache.remove(first)
            }
            return result
        }
    }

    private fun parseUsers(root: JSONObject): List<EmbedData> {
        val arr = root.optJSONArray("users") ?: return emptyList()
        val out = ArrayList<EmbedData>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val id = o.optString("id", "").trim()
            if (id.isEmpty()) continue
            val guild = o.optJSONObject("guild")
            val guildName = guild?.optString("name", "")?.trim().orEmpty()
            val intro = o.optString("intro", "").trim()
            out.add(
                EmbedData(
                    type = "user",
                    id = id,
                    title = o.optString("name", "用户").trim().ifBlank { "用户" },
                    subtitle = guildName.ifBlank { intro },
                    avatar = o.optString("avatar", ""),
                    url = "/user/" + id,
                ),
            )
        }
        return out
    }

    private fun parsePosts(root: JSONObject): List<EmbedData> {
        val arr = root.optJSONArray("posts") ?: return emptyList()
        val out = ArrayList<EmbedData>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val id = o.optString("id", "").trim()
            if (id.isEmpty()) continue
            val author = o.optString("user_name", "").trim()
            val guild = o.optString("guild_name", "").trim()
            out.add(
                EmbedData(
                    type = "post",
                    id = id,
                    title = o.optString("title", "帖子").trim().ifBlank { "帖子" },
                    subtitle = listOf(author, guild).filter { it.isNotBlank() }.joinToString(" · "),
                    avatar = o.optString("user_avatar", ""),
                    url = "/post/" + id,
                ),
            )
        }
        return out
    }

    private fun parseArticles(root: JSONObject): List<EmbedData> {
        val arr = root.optJSONArray("articles") ?: return emptyList()
        val out = ArrayList<EmbedData>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val id = o.optString("id", "").trim()
            if (id.isEmpty()) continue
            val author = o.optString("author_name", "").trim()
            val guild = o.optString("guild_name", "").trim()
            out.add(
                EmbedData(
                    type = "article",
                    id = id,
                    title = o.optString("title", "文章").trim().ifBlank { "文章" },
                    subtitle = listOf(author, guild).filter { it.isNotBlank() }.joinToString(" · "),
                    avatar = o.optString("author_avatar", ""),
                    url = "/article/" + id,
                ),
            )
        }
        return out
    }
}
