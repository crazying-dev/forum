package top.crazying.forum.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
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
        // 每个请求都带上 X-Client-Platform / X-Client-Version（最低版本闸门）
        .addInterceptor(Constants.clientHeaderInterceptor())
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
        } else if (Constants.isVersionTooLow(result.status, result.str("code"))) {
            // 服务端 426 / VERSION_TOO_LOW：交给 App 弹不可绕过的强制更新窗
            runCatching { App.onVersionTooLow(result.obj()) }
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

    suspend fun login(
        name: String = "",
        email: String = "",
        password: String,
        captchaToken: String = "",
    ): ApiResult {
        val body = JSONObject()
        if (name.isNotBlank()) body.put("name", name.trim())
        if (email.isNotBlank()) body.put("email", email.trim())
        body.put("password", password)
        val result = post("/api/user/login", Captcha.withToken(body, captchaToken))
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

    suspend fun register(
        name: String,
        email: String,
        password: String,
        captchaToken: String = "",
    ): ApiResult {
        val body = JSONObject()
            .put("name", name.trim())
            .put("email", email.trim())
            .put("password", password)
        val result = post("/api/user/register", Captcha.withToken(body, captchaToken))
        if (result.ok) {
            adoptUser(result)
            if (App.user.value == null) runCatching { me() }
            prefs.lastName = name.trim()
        }
        return result
    }

    suspend fun sendRegisterCode(email: String, captchaToken: String = ""): ApiResult =
        post(
            "/api/email/send-register-code",
            Captcha.withToken(JSONObject().put("email", email.trim()), captchaToken),
        )

    /** 注销账号验证码：发到当前绑定邮箱（需登录；未绑定有效邮箱服务端返回 400）。 */
    suspend fun sendDeleteAccountCode(captchaToken: String = ""): ApiResult =
        post("/api/email/send-delete-account-code", Captcha.withToken(JSONObject(), captchaToken))

    /**
     * 自助注销账号。
     *
     * @param mode     "purge" 彻底删除 / "anonymize" 匿名化保留
     * @param password 账号密码（与 [code] 二选一，可为 null）
     * @param code     邮箱验证码（与 [password] 二选一，可为 null）
     */
    suspend fun deleteAccount(
        mode: String,
        password: String?,
        code: String?,
        captchaToken: String = "",
    ): ApiResult {
        val body = JSONObject()
            .put("mode", mode)
            .put("confirm", "注销账号")
        if (!password.isNullOrBlank()) body.put("password", password)
        if (!code.isNullOrBlank()) body.put("code", code.trim())
        return post("/api/user/delete", Captcha.withToken(body, captchaToken))
    }

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

    /**
     * 上传头像（multipart，字段名 `avatar`，与 Web 端一致）。
     *
     * 服务端会裁剪压缩为 400×400 WebP 并直接落库，成功后调用方应再调一次 [me] 刷新本地用户。
     */
    suspend fun uploadAvatar(bytes: ByteArray, filename: String, mimeType: String): ApiResult =
        withContext(Dispatchers.IO) {
            try {
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        "avatar",
                        filename.ifBlank { "avatar.jpg" },
                        bytes.toRequestBody(mimeType.toMediaTypeOrNull()),
                    )
                    .build()
                val request = Request.Builder()
                    .url(Constants.BASE_URL + "/api/user/avatar/upload")
                    .header("User-Agent", Constants.CLIENT_UA)
                    .header("Accept", "application/json, text/plain, */*")
                    .post(body)
                    .build()
                val result = callOnce(request)
                if (result.status == 401) {
                    runCatching { App.onUnauthorized() }
                } else if (Constants.isVersionTooLow(result.status, result.str("code"))) {
                    runCatching { App.onVersionTooLow(result.obj()) }
                }
                result
            } catch (e: Exception) {
                ApiResult(0, null, "网络错误，请检查网络连接后重试")
            }
        }

    // ────────────────── 账号安全（修改密码 / 更换邮箱） ──────────────────

    /** 修改密码第 1 步：发送 6 位验证码到当前绑定邮箱。 */
    suspend fun sendChangePasswordCode(captchaToken: String = ""): ApiResult =
        post("/api/email/send-change-password-code", Captcha.withToken(JSONObject(), captchaToken))

    /** 修改密码第 2 步：凭邮箱验证码设置新密码（成功后服务端会清 cookie，需重新登录）。 */
    suspend fun changePassword(code: String, newPassword: String): ApiResult =
        post(
            "/api/user/password",
            JSONObject().put("code", code.trim()).put("new_password", newPassword),
        )

    /** 更换邮箱第 1 步：发送验证码到「当前绑定邮箱」（身份确认）。 */
    suspend fun sendChangeEmailOldCode(captchaToken: String = ""): ApiResult =
        post("/api/email/send-change-email-old-code", Captcha.withToken(JSONObject(), captchaToken))

    /** 更换邮箱第 2 步：发送验证码到「新邮箱」（可达性验证）。 */
    suspend fun sendChangeEmailCode(email: String, captchaToken: String = ""): ApiResult =
        post(
            "/api/email/send-change-email-code",
            Captcha.withToken(JSONObject().put("email", email.trim()), captchaToken),
        )

    /** 更换邮箱第 3 步：凭两枚验证码完成换绑。 */
    suspend fun changeEmail(email: String, oldCode: String, code: String): ApiResult {
        val body = JSONObject()
            .put("email", email.trim())
            .put("old_code", oldCode.trim())
            .put("code", code.trim())
        val result = post("/api/user/email", body)
        if (result.ok) adoptUser(result)
        return result
    }

    // ────────────────── 人机验证（滑块拼图） ──────────────────

    /**
     * 申请一次滑块拼图挑战。
     *
     * 返回 `{success, token, bg, piece, y, width, height, piece_size}`（`bg` / `piece`
     * 是 data URL PNG）；服务端未启用人机验证时返回 `{success: true, enabled: false}`。
     *
     * [provider] 非空时强制指定（`"slider"` = Turnstile 解不出来时的回退通道）。
     */
    suspend fun captchaChallenge(provider: String = ""): ApiResult =
        post(Captcha.challengePath(provider))

    /** 提交滑块 x 坐标；成功返回原 token，失败返回 400 + 可读文案。 */
    suspend fun captchaVerify(captchaToken: String, captchaX: Int): ApiResult =
        post(
            Captcha.VERIFY_PATH,
            JSONObject()
                .put(Captcha.FIELD_TOKEN, captchaToken)
                .put(Captcha.FIELD_X, captchaX),
        )

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

    /** 点赞 / 取消点赞评论；返回 `{success, liked, likes}`。 */
    suspend fun likeComment(commentId: String): ApiResult = post("/api/comments/$commentId/like")

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

    // ────────────────── 应用更新 / 彩蛋 ──────────────────

    /**
     * 版本检查。
     *
     * 服务端读仓库根的 `app_releases.json`，返回
     * `{available, latest, mandatory, message, release:{version,url,filename,size,sha256,notes}}`。
     */
    suspend fun checkUpdate(version: String = Constants.APP_VERSION): ApiResult = get(
        Constants.CHECK_UPDATE_PATH,
        mapOf("platform" to Constants.PLATFORM_ANDROID, "version" to version),
    )

    /** 随机一条彩蛋（服务端从 `EasterEgg/1.json` 抽）。 */
    suspend fun easterEgg(): ApiResult = get(Constants.EASTER_EGG_PATH)

    /** 抓取站外 JSON（每日一言）；不走本服务的错误口径，失败返回 status=0。 */
    suspend fun fetchExternalJson(url: String): ApiResult = request("GET", url)

    /**
     * 抓取纯文本资源（WIKI 的 markdown / license 等）。
     *
     * 与 [request] 不同：不解析 JSON，直接返回响应正文；任何异常 / 非 2xx 返回 null。
     */
    suspend fun fetchText(url: String): String? = withContext(Dispatchers.IO) {
        try {
            val absolute = if (url.startsWith("http://") || url.startsWith("https://")) url
            else Constants.BASE_URL + "/" + url.trimStart('/')
            val request = Request.Builder()
                .url(absolute)
                .header("User-Agent", Constants.CLIENT_UA)
                .build()
            client.newCall(request).execute().use { response ->
                if (response.code in 200..299) response.body?.string() else null
            }
        } catch (e: Exception) {
            null
        }
    }
}
