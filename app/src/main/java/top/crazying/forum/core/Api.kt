package top.crazying.forum.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * 统一接口返回包装。
 *
 * 解析口径「宽松」，与 Windows 端 `app/api.py` 的 `Result` 一致：
 * 部分接口（如 `/api/posts`）不返回 `success` 字段，
 * 只要 HTTP < 400 且能解出 JSON（对象或数组）就算成功；错误文案优先取 `message`。
 */
class ApiResult(
    val status: Int,
    val data: Any?,
    val error: String? = null,
) {

    val ok: Boolean
        get() {
            if (error != null) return false
            if (status >= 400) return false
            val d = data
            if (d == null) return false
            if (d is JSONObject && !d.optBoolean("success", true)) return false
            return true
        }

    val message: String
        get() {
            val d = data
            if (d is JSONObject) {
                for (k in MESSAGE_KEYS) {
                    val v = d.optString(k, "").trim()
                    if (v.isNotEmpty() && v != "null") return v
                }
            }
            if (error != null) return error
            return when {
                status == 0 -> "网络错误，请检查网络连接后重试"
                status == 401 -> "请先登录"
                status == 403 -> "没有权限"
                status == 404 -> "内容不存在或已被删除"
                status == 429 -> "操作过于频繁，请稍后再试"
                status >= 500 -> "服务器开小差了，请稍后再试"
                status >= 400 -> "请求失败（HTTP $status）"
                else -> "请求失败"
            }
        }

    fun obj(): JSONObject? = data as? JSONObject

    fun arr(): JSONArray? = data as? JSONArray

    fun str(key: String, def: String = ""): String {
        val o = obj() ?: return def
        if (!o.has(key) || o.isNull(key)) return def
        return o.optString(key, def)
    }

    fun int(key: String, def: Int = 0): Int {
        val o = obj() ?: return def
        if (!o.has(key) || o.isNull(key)) return def
        return o.optInt(key, def)
    }

    fun bool(key: String, def: Boolean = false): Boolean {
        val o = obj() ?: return def
        if (!o.has(key) || o.isNull(key)) return def
        return o.optBoolean(key, def)
    }

    fun jsonObj(key: String): JSONObject? {
        val o = obj() ?: return null
        return o.optJSONObject(key)
    }

    /** 取 `key` 对应的数组；若自身就是数组则直接返回（`/api/world/ALL`）。 */
    fun rows(key: String? = null): List<JSONObject> {
        val arr = when {
            key == null -> data as? JSONArray
            else -> obj()?.optJSONArray(key)
        } ?: return emptyList()
        val out = ArrayList<JSONObject>(arr.length())
        for (i in 0 until arr.length()) {
            arr.optJSONObject(i)?.let { out.add(it) }
        }
        return out
    }

    /** 列表型接口的键名在不同接口上不统一，按优先级依次尝试。 */
    fun rowsAny(vararg keys: String): List<JSONObject> {
        for (k in keys) {
            val rows = rows(k)
            if (rows.isNotEmpty()) return rows
        }
        return rows(null)
    }

    private companion object {
        val MESSAGE_KEYS = listOf("message", "error", "msg", "detail")
    }
}

/**
 * 妖精论坛后端接口层（唯一出网入口）。
 *
 * 全部方法均为 `suspend`，内部切 `Dispatchers.IO`，调用方在协程里直接用。
 */
class Api(private val prefs: Prefs) {

    private val jar = PrefsCookieJar(prefs)

    private val client: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(jar)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    fun clearCookies() = jar.clear()

    /** 是否有本地凭证（粗略判断，真正有效性由服务端决定）。 */
    val hasCredentials: Boolean
        get() = App.user.value != null || prefs.cookieStore.isNotEmpty()

    // ────────────────── 底层请求 ──────────────────

    private fun buildUrl(path: String, params: Map<String, Any?>?): String {
        val base = if (path.startsWith("http://") || path.startsWith("https://")) path
        else Constants.BASE_URL + "/" + path.trimStart('/')
        if (params.isNullOrEmpty()) return base
        val parsed = base.toHttpUrlOrNull() ?: return base
        val b = parsed.newBuilder()
        for ((k, v) in params) {
            if (v == null) continue
            val s = v.toString()
            if (s.isEmpty()) continue
            b.addQueryParameter(k, s)
        }
        return b.build().toString()
    }

    private fun parse(response: Response): ApiResult {
        val text = try {
            response.body?.string().orEmpty()
        } catch (e: Exception) {
            ""
        }
        var parsed: Any? = null
        val t = text.trim()
        if (t.isNotEmpty()) {
            parsed = try {
                if (t.startsWith("[")) JSONArray(t) else JSONObject(t)
            } catch (e: Exception) {
                null
            }
        }
        return ApiResult(response.code, parsed, null)
    }

    private fun callOnce(request: Request): ApiResult {
        return try {
            client.newCall(request).execute().use { response -> parse(response) }
        } catch (e: Exception) {
            ApiResult(0, null, "网络错误，请检查网络连接后重试")
        }
    }

    suspend fun request(
        method: String,
        path: String,
        params: Map<String, Any?>? = null,
        json: JSONObject? = null,
    ): ApiResult = withContext(Dispatchers.IO) {
        val url = buildUrl(path, params)
        val verb = method.uppercase()
        val body: RequestBody? = when {
            json != null -> json.toString().toRequestBody(jsonMedia)
            verb == "POST" || verb == "PUT" || verb == "PATCH" -> "{}".toRequestBody(jsonMedia)
            else -> null
        }
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", Constants.CLIENT_UA)
            .header("Accept", "application/json, text/plain, */*")
            .header("Accept-Language", "zh-CN,zh;q=0.9")
            .method(verb, body)
            .build()

        // GET 允许重试一次（弱网下很常见）；写操作绝不重试，避免重复发帖/评论。
        var result = callOnce(request)
        if (result.status == 0 && verb == "GET") {
            result = callOnce(request)
        }
        if (result.status == 401) {
            runCatching { App.onUnauthorized() }
        }
        result
    }

    suspend fun get(path: String, params: Map<String, Any?>? = null): ApiResult =
        request("GET", path, params)

    suspend fun post(path: String, json: JSONObject? = null): ApiResult =
        request("POST", path, null, json ?: JSONObject())

    /** 登录 / 拉用户信息后同步全局会话状态。 */
    private fun adoptUser(result: ApiResult) {
        App.setUser(result.jsonObj("user"))
    }

    // ────────────────── 认证 ──────────────────

    suspend fun login(name: String = "", email: String = "", password: String): ApiResult {
        val body = JSONObject()
        if (name.isNotBlank()) body.put("name", name.trim())
        if (email.isNotBlank()) body.put("email", email.trim())
        body.put("password", password)
        val result = post("/api/user/login", body)
        if (result.ok) {
            adoptUser(result)
            val who = name.ifBlank { email }.trim()
            if (who.isNotEmpty()) prefs.lastName = who
        }
        return result
    }

    suspend fun logout(): ApiResult {
        val result = post("/api/user/logout")
        App.logoutLocal()
        return result
    }

    suspend fun register(name: String, email: String, password: String): ApiResult {
        val body = JSONObject()
            .put("name", name.trim())
            .put("email", email.trim())
            .put("password", password)
        val result = post("/api/user/register", body)
        if (result.ok) {
            adoptUser(result)
            if (App.user.value == null) runCatching { me() }
            prefs.lastName = name.trim()
        }
        return result
    }

    suspend fun sendRegisterCode(email: String): ApiResult =
        post("/api/email/send-register-code", JSONObject().put("email", email.trim()))

    suspend fun me(): ApiResult {
        val result = get("/api/user/info")
        if (result.ok) adoptUser(result)
        return result
    }

    suspend fun updateProfile(fields: JSONObject): ApiResult {
        val result = request("PUT", "/api/user/info", null, fields)
        if (result.ok) {
            adoptUser(result)
            if (App.user.value == null) runCatching { me() }
        }
        return result
    }

    // ────────────────── 帖子 ──────────────────

    suspend fun posts(
        page: Int = 1,
        pageSize: Int = Constants.PAGE_SIZE,
        category: String? = null,
        sort: String? = null,
    ): ApiResult = get(
        "/api/posts",
        mapOf("page" to page, "page_size" to pageSize, "category" to category, "sort" to sort)
    )

    suspend fun randomPosts(limit: Int = Constants.RANDOM_LIMIT): ApiResult =
        get("/api/posts/random", mapOf("limit" to limit))

    suspend fun getPost(postId: String): ApiResult = get("/api/posts/$postId")

    suspend fun createPost(title: String, content: String, category: String): ApiResult {
        val body = JSONObject()
            .put("title", title.trim())
            .put("content", content)
            .put("category", category)
        return post("/api/posts/create", body)
    }

    suspend fun likePost(postId: String): ApiResult = post("/api/posts/$postId/like")

    suspend fun favoritePost(postId: String): ApiResult = post("/api/posts/$postId/favorite")

    suspend fun deletePost(postId: String): ApiResult = post("/api/posts/$postId/delete")

    // ────────────────── 评论 ──────────────────

    suspend fun comments(postId: String, page: Int = 1, pageSize: Int = 50): ApiResult =
        get("/api/posts/$postId/comments", mapOf("page" to page, "page_size" to pageSize))

    suspend fun createComment(postId: String, content: String, parentId: String? = null): ApiResult {
        val body = JSONObject().put("content", content.trim())
        if (!parentId.isNullOrBlank()) body.put("parent_id", parentId)
        return post("/api/posts/$postId/comments/create", body)
    }

    suspend fun deleteComment(commentId: String): ApiResult = post("/api/comments/$commentId/delete")

    // ────────────────── 搜索 ──────────────────

    suspend fun search(
        keyword: String,
        page: Int = 1,
        pageSize: Int = Constants.PAGE_SIZE,
        type: String = "both",
    ): ApiResult = get(
        "/api/search",
        mapOf("k" to keyword, "page" to page, "page_size" to pageSize, "type" to type)
    )

    // ────────────────── 用户 ──────────────────

    suspend fun userInfo(userId: String): ApiResult = get("/api/user/$userId")

    suspend fun follow(userId: String): ApiResult = post("/api/user/$userId/follow")

    suspend fun userPosts(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get("/api/user/$userId/posts", mapOf("page" to page, "page_size" to pageSize))

    suspend fun userFavorites(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get("/api/user/$userId/favorites", mapOf("page" to page, "page_size" to pageSize))

    suspend fun userComments(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get("/api/user/$userId/comments", mapOf("page" to page, "page_size" to pageSize))

    suspend fun following(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get("/api/user/$userId/following", mapOf("page" to page, "page_size" to pageSize))

    suspend fun followers(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get("/api/user/$userId/followers", mapOf("page" to page, "page_size" to pageSize))

    // ────────────────── 世界频道 ──────────────────

    /** 服务端返回裸 JSON 数组（最近 100 条）。 */
    suspend fun worldAll(): ApiResult = get("/api/world/ALL")

    suspend fun worldSend(content: String, parentId: String? = null): ApiResult {
        val body = JSONObject().put("content", content.trim())
        if (!parentId.isNullOrBlank()) body.put("parent_id", parentId)
        return post("/api/world/Send", body)
    }

    // ────────────────── 杂项 ──────────────────

    suspend fun healthz(): ApiResult = get(Constants.HEALTHZ_PATH)
}
