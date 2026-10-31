package top.crazying.forum.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.Cookie
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
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
                    if (v.isNotEmpty() && v != "null") {
                        return if (v == "CAPTCHA_REQUIRED") "请先完成人机验证" else v
                    }
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

    /** ALTCHA 求解串行化，避免并发请求同时算同一份挑战。 */
    private val captchaMutex = Mutex()
    @Volatile private var captchaDisabledUntil = 0L
    @Volatile private var grantValue: String? = null
    @Volatile private var grantExpiresAt = 0L

    private val client: OkHttpClient = OkHttpClient.Builder()
        // 每个请求都带上 X-Client-Platform / X-Client-Version
        .addInterceptor(Constants.clientHeaderInterceptor())
        // ov2 的 CSRF 要求同源 Origin/Referer；原生客户端显式自报来源。
        .addInterceptor(originInterceptor())
        .cookieJar(jar)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    fun clearCookies() = jar.clear()

    /** 站内 API 路径统一拼 canonical 前缀，页面不得自行拼 `/ov2/api`。 */
    private fun api(path: String): String =
        Constants.API_PREFIX + "/" + path.trimStart('/')

    /**
     * 对同源请求补 `Origin` / `Referer`。
     *
     * ouo 的 CSRF 中间件要求非 GET 请求带同源 Origin/Referer；OkHttp 默认不带。
     * 只对 `BASE_URL` 同源请求生效，避免把站点来源带给第三方（每日一言、GitHub）。
     */
    private fun originInterceptor(): Interceptor = Interceptor { chain ->
        val request = chain.request()
        val base = Constants.BASE_URL.toHttpUrlOrNull()
        val sameOrigin = base != null &&
            request.url.host == base.host &&
            request.url.port == base.port &&
            request.url.scheme == base.scheme
        if (!sameOrigin) {
            chain.proceed(request)
        } else {
            chain.proceed(
                request.newBuilder()
                    .header("Origin", Constants.BASE_URL)
                    .header("Referer", Constants.BASE_URL + "/")
                    .build(),
            )
        }
    }

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

    /** 一次底层 HTTP 请求（不做 ALTCHA，不改全局会话状态）。 */
    private fun execute(
        method: String,
        path: String,
        params: Map<String, Any?>?,
        json: JSONObject?,
    ): ApiResult {
        val url = buildUrl(path, params)
        val verb = method.uppercase()
        val body: RequestBody? = when {
            json != null -> json.toString().toRequestBody(jsonMedia)
            verb == "POST" || verb == "PUT" || verb == "PATCH" || verb == "DELETE" ->
                "{}".toRequestBody(jsonMedia)
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
        return result
    }

    /** 401 清会话；426 弹强制更新。 */
    private fun handleStatus(result: ApiResult) {
        if (result.status == 401) {
            runCatching { App.onUnauthorized() }
        } else if (Constants.isVersionTooLow(result.status, result.str("code"))) {
            runCatching { App.onVersionTooLow(result.obj()) }
        }
    }

    suspend fun request(
        method: String,
        path: String,
        params: Map<String, Any?>? = null,
        json: JSONObject? = null,
        captcha: Boolean = false,
    ): ApiResult = withContext(Dispatchers.IO) {
        try {
            val verb = method.uppercase()
            var proof: ProofResult = ProofResult.None
            if (captcha) {
                proof = ensureCaptchaProof()
                when (proof) {
                    is ProofResult.Cancelled -> return@withContext ApiResult(0, null, "已取消安全验证")
                    is ProofResult.Failed -> return@withContext ApiResult(0, null, proof.message)
                    else -> Unit
                }
            }
            var result = execute(verb, path, params, applyProof(json, proof))
            if (captcha && isCaptchaRequired(result)) {
                // grant 可能过期 / 绑定 IP 变化：清缓存后重新求解，只重试一次。
                invalidateCaptcha()
                val retry = ensureCaptchaProof(force = true)
                when (retry) {
                    is ProofResult.Cancelled -> return@withContext ApiResult(0, null, "已取消安全验证")
                    is ProofResult.Failed -> return@withContext ApiResult(0, null, retry.message)
                    else -> result = execute(verb, path, params, applyProof(json, retry))
                }
            }
            handleStatus(result)
            result
        } catch (e: CancellationException) {
            throw e
        } catch (e: OutOfMemoryError) {
            ApiResult(0, null, "设备内存不足，请重试")
        } catch (t: Throwable) {
            // 兜底文案固定，避免把内部异常 message 直接展示给用户。
            ApiResult(0, null, "网络错误，请检查网络连接后重试")
        }
    }

    suspend fun get(path: String, params: Map<String, Any?>? = null): ApiResult =
        request("GET", path, params)

    suspend fun post(path: String, json: JSONObject? = null): ApiResult =
        request("POST", path, null, json ?: JSONObject())

    private suspend fun patch(path: String, json: JSONObject): ApiResult =
        request("PATCH", path, null, json)

    private suspend fun delete(path: String): ApiResult = request("DELETE", path)

    /** 登录 / 拉用户信息后同步全局会话状态。 */
    private fun adoptUser(result: ApiResult) {
        App.setUser(result.jsonObj("user"))
    }

    // ────────────────── ALTCHA 会话（grant 缓存） ──────────────────

    private sealed interface ProofResult {
        data object None : ProofResult
        data class Ready(val grant: String) : ProofResult
        data object Cancelled : ProofResult
        data class Failed(val message: String) : ProofResult
    }

    private fun applyProof(json: JSONObject?, proof: ProofResult): JSONObject? {
        if (proof !is ProofResult.Ready) return json
        val out = if (json == null) JSONObject() else JSONObject(json.toString())
        if (proof.grant.isNotBlank()) out.put("grant", proof.grant)
        return out
    }

    private fun isCaptchaRequired(result: ApiResult): Boolean {
        if (result.status != 400) return false
        val message = result.message
        return message.contains("CAPTCHA_REQUIRED") ||
            message.contains("请先完成人机验证") ||
            message.contains("人机验证")
    }

    private fun invalidateCaptcha() {
        grantValue = null
        grantExpiresAt = 0L
    }

    /** 失败弹窗等待用户选择：true = 重试，false = 取消。 */
    private suspend fun awaitCaptchaRetry(message: String): Boolean =
        AltchaUi.fail(message) == Decision.Retry

    /**
     * 确保拿到可复用的 grant：
     * 1) 已缓存且未过期 → 直接复用；
     * 2) 服务端未启用 → 返回 None（不带字段）；
     * 3) 否则拉 challenge → 本地求解 → `/captcha/verify` 换 grant；
     *    求解失败（超时/未命中/异常/OOM）在弹窗内提供「重试 / 取消」，重试会重新拉 challenge。
     */
    private suspend fun ensureCaptchaProof(force: Boolean = false): ProofResult =
        captchaMutex.withLock {
            val now = System.currentTimeMillis()
            if (!force && captchaDisabledUntil > now) return@withLock ProofResult.None
            if (!force) {
                val cached = grantValue
                if (!cached.isNullOrBlank() && grantExpiresAt > now) {
                    return@withLock ProofResult.Ready(cached)
                }
            }

            var workers = Altcha.defaultWorkers()
            var oomRetried = false

            // 进入验证即展示转圈：challenge 拉取期间也可取消（重试后同理）。
            AltchaUi.begin()
            try {
                while (true) {
                    try {
                        // 1) 拉 challenge（首次与每次重试都重新拉，避免用过期/一次性挑战）。
                        val challengeRes = execute("GET", api("captcha/challenge"), null, null)
                        if (AltchaUi.isCancelled()) {
                            AltchaUi.end()
                            return@withLock ProofResult.Cancelled
                        }
                        if (challengeRes.status == 404 ||
                            challengeRes.message.contains("CAPTCHA_DISABLED")
                        ) {
                            captchaDisabledUntil = System.currentTimeMillis() + 10 * 60_000L
                            return@withLock ProofResult.None
                        }
                        if (!challengeRes.ok) return@withLock ProofResult.Failed(challengeRes.message)
                        val challenge = Altcha.parse(challengeRes.obj())
                            ?: return@withLock ProofResult.Failed("安全验证数据异常")
                        if (Altcha.isExpired(challenge)) {
                            return@withLock ProofResult.Failed("安全验证已过期，请重试")
                        }

                        // 2) 求解：worker 上限 4、90s 超时；OOM 时 worker 减半重试同一挑战一次。
                        var outcome: SolveOutcome? = null
                        var failure: String? = null
                        solve@ while (true) {
                            try {
                                outcome = Altcha.solve(
                                    challenge = challenge,
                                    workers = workers,
                                    deadlineMs = 90_000L,
                                    isCancelled = { AltchaUi.isCancelled() },
                                )
                                break@solve
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: OutOfMemoryError) {
                                if (!oomRetried) {
                                    oomRetried = true
                                    workers = (workers / 2).coerceAtLeast(1)
                                    continue@solve
                                }
                                failure = "设备内存不足，请重试"
                                break@solve
                            } catch (t: Throwable) {
                                failure = "安全验证失败，请重试"
                                break@solve
                            }
                        }

                        if (failure != null) {
                            if (awaitCaptchaRetry(failure)) {
                                workers = Altcha.defaultWorkers()
                                oomRetried = false
                                continue
                            }
                            return@withLock ProofResult.Cancelled
                        }

                        // 3) 结果处理
                        when (val result = outcome ?: SolveOutcome.NoMatch) {
                            is SolveOutcome.Solved -> {
                                if (AltchaUi.isCancelled()) {
                                    AltchaUi.end()
                                    return@withLock ProofResult.Cancelled
                                }
                                val payload = Altcha.payload(challenge, result.solution)
                                val verifyRes = execute(
                                    "POST",
                                    api("captcha/verify"),
                                    null,
                                    JSONObject().put("altcha", payload),
                                )
                                if (verifyRes.status == 404 ||
                                    verifyRes.message.contains("CAPTCHA_DISABLED")
                                ) {
                                    captchaDisabledUntil = System.currentTimeMillis() + 10 * 60_000L
                                    return@withLock ProofResult.None
                                }
                                val grant = verifyRes.str("grant").trim()
                                if (!verifyRes.ok || grant.isEmpty()) {
                                    val reason = when {
                                        verifyRes.status == 0 -> "网络异常，请检查连接后重试"
                                        !verifyRes.ok -> "安全验证失败，请重试"
                                        else -> "安全验证返回异常"
                                    }
                                    if (awaitCaptchaRetry(reason)) {
                                        workers = Altcha.defaultWorkers()
                                        oomRetried = false
                                        continue
                                    }
                                    return@withLock ProofResult.Cancelled
                                }
                                if (!AltchaUi.finishSuccess()) return@withLock ProofResult.Cancelled
                                val ttl = verifyRes.int("expires_in", 300).coerceAtLeast(60) * 1000L
                                grantValue = grant
                                grantExpiresAt = System.currentTimeMillis() + ttl - 10_000L
                                return@withLock ProofResult.Ready(grant)
                            }

                            SolveOutcome.TimedOut -> {
                                if (awaitCaptchaRetry("安全验证超时，请重试")) {
                                    workers = Altcha.defaultWorkers()
                                    oomRetried = false
                                    continue
                                }
                                return@withLock ProofResult.Cancelled
                            }

                            SolveOutcome.NoMatch -> {
                                if (awaitCaptchaRetry("安全验证失败，请重试")) {
                                    workers = Altcha.defaultWorkers()
                                    oomRetried = false
                                    continue
                                }
                                return@withLock ProofResult.Cancelled
                            }

                            SolveOutcome.Cancelled -> {
                                AltchaUi.end()
                                return@withLock ProofResult.Cancelled
                            }
                        }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (t: Throwable) {
                        // 兜底：未预期异常收敛为失败，不让页面卡在 busy。
                        val message = if (t is OutOfMemoryError) "设备内存不足，请重试"
                        else "安全验证失败，请重试"
                        if (AltchaUi.isCancelled()) {
                            AltchaUi.end()
                            return@withLock ProofResult.Cancelled
                        }
                        if (AltchaUi.phase.value == Phase.Idle) {
                            return@withLock ProofResult.Failed(message)
                        }
                        if (awaitCaptchaRetry(message)) {
                            workers = Altcha.defaultWorkers()
                            oomRetried = false
                        } else {
                            return@withLock ProofResult.Cancelled
                        }
                    }
                }
            } finally {
                AltchaUi.end()
            }
            // while (true) 内部所有业务路径都会 return；此行仅用于 Kotlin 类型收敛。
            return@withLock ProofResult.Failed("安全验证失败，请重试")
        }

    // ────────────────── 认证 ──────────────────

    suspend fun login(
        name: String = "",
        email: String = "",
        password: String,
    ): ApiResult {
        val identifier = name.ifBlank { email }.trim()
        val body = JSONObject()
            .put("name", identifier)
            .put("password", password)
            .put("remember", true)
        val result = request("POST", api("auth/login"), json = body, captcha = true)
        if (result.ok) {
            // ov2 登录只返回 {success,id}，用户资料需要再拉一次。
            val who = me()
            if (!who.ok) return who
            if (identifier.isNotEmpty()) prefs.lastName = identifier
        }
        return result
    }

    suspend fun logout(): ApiResult {
        val result = post(api("auth/logout"))
        App.logoutLocal()
        return result
    }

    suspend fun register(
        name: String,
        email: String,
        password: String,
        code: String,
    ): ApiResult {
        val body = JSONObject()
            .put("name", name.trim())
            .put("email", email.trim())
            .put("password", password)
            .put("code", code.trim())
        val result = request("POST", api("auth/register"), json = body, captcha = true)
        if (result.ok) {
            prefs.lastName = name.trim()
            val who = me()
            if (!who.ok) return who
        }
        return result
    }

    suspend fun sendRegisterCode(email: String): ApiResult =
        request(
            "POST",
            api("auth/register/code"),
            json = JSONObject().put("email", email.trim()),
            captcha = true,
        )

    /** 自助注销：ov2 要求密码 + 输入当前用户名（confirmName）。 */
    suspend fun deleteAccount(
        mode: String,
        password: String,
        confirmName: String,
    ): ApiResult = post(
        api("users/me/delete"),
        JSONObject()
            .put("mode", mode)
            .put("password", password)
            .put("confirmName", confirmName),
    )

    suspend fun me(): ApiResult {
        val result = get(api("users/me"))
        if (result.ok) {
            adoptUser(result)
        } else if (result.status == 200 && result.message.contains("未登录")) {
            // ov2 的 /users/me 未登录返回 200 + success:false，不是 401。
            runCatching { App.onUnauthorized() }
        }
        return result
    }

    suspend fun updateProfile(fields: JSONObject): ApiResult {
        val result = patch(api("users/me"), fields)
        if (result.ok) runCatching { me() }
        return result
    }

    /** 上传头像（multipart 字段 `avatar`）。 */
    suspend fun uploadAvatar(bytes: ByteArray, filename: String, mimeType: String): ApiResult =
        multipart(
            path = "users/me/avatar",
            field = "avatar",
            bytes = bytes,
            filename = filename,
            mimeType = mimeType,
        )

    /** 通用 multipart 上传（头像 / 正文图片）。 */
    private suspend fun multipart(
        path: String,
        field: String,
        bytes: ByteArray,
        filename: String,
        mimeType: String,
        extra: Map<String, String> = emptyMap(),
    ): ApiResult = withContext(Dispatchers.IO) {
        try {
            val builder = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    field,
                    filename.ifBlank { "upload.bin" },
                    bytes.toRequestBody(mimeType.toMediaTypeOrNull()),
                )
            for ((k, v) in extra) builder.addFormDataPart(k, v)
            val request = Request.Builder()
                .url(buildUrl(api(path), null))
                .header("User-Agent", Constants.CLIENT_UA)
                .header("Accept", "application/json, text/plain, */*")
                .post(builder.build())
                .build()
            val result = callOnce(request)
            handleStatus(result)
            result
        } catch (e: Exception) {
            ApiResult(0, null, "网络错误，请检查网络连接后重试")
        }
    }

    /** 发送正文/评论/世界频道图片（scene 决定服务端用途）。 */
    suspend fun uploadImage(
        bytes: ByteArray,
        filename: String,
        mimeType: String,
        scene: String = "post_image",
    ): ApiResult = multipart(
        path = "media/images",
        field = "file",
        bytes = bytes,
        filename = filename,
        mimeType = mimeType,
        extra = mapOf("scene" to scene),
    )

    /** 引用卡片批量数据（users/posts/articles 都是 id 列表）。 */
    suspend fun embeds(
        users: List<String> = emptyList(),
        posts: List<String> = emptyList(),
        articles: List<String> = emptyList(),
    ): ApiResult = get(
        api("embeds"),
        mapOf(
            "users" to users.joinToString(","),
            "posts" to posts.joinToString(","),
            "articles" to articles.joinToString(","),
        ),
    )

    // ────────────────── 账号安全（改密 / 换绑邮箱） ──────────────────

    /** ov2 改密：当前密码 + 新密码；成功后服务端会重签当前会话。 */
    suspend fun changePassword(currentPassword: String, newPassword: String): ApiResult =
        patch(
            api("users/me"),
            JSONObject().put("password", newPassword).put("current_password", currentPassword),
        )

    /** 换绑第 1 步：向当前邮箱发验证码。 */
    suspend fun sendChangeEmailOldCode(): ApiResult =
        post(api("users/me/email-change/code"))

    /** 换绑第 2 步：验证当前邮箱验证码。 */
    suspend fun verifyChangeEmailOld(code: String): ApiResult =
        post(api("users/me/email-change/verify-old"), JSONObject().put("code", code.trim()))

    /** 换绑第 3 步：向新邮箱发验证码。 */
    suspend fun sendChangeEmailNewCode(newEmail: String): ApiResult =
        post(api("users/me/email-change/new-code"), JSONObject().put("newEmail", newEmail.trim()))

    /** 换绑第 4 步：凭新邮箱验证码完成换绑。 */
    suspend fun confirmChangeEmail(code: String): ApiResult =
        post(api("users/me/email-change/confirm"), JSONObject().put("code", code.trim()))

    // ────────────────── 帖子 ──────────────────

    suspend fun posts(
        page: Int = 1,
        pageSize: Int = Constants.PAGE_SIZE,
        category: String? = null,
    ): ApiResult = get(
        api("posts"),
        mapOf("page" to page, "page_size" to pageSize, "category" to category),
    )

    /** ov2 每次最多返回 100 条；服务端忽略 limit 参数。 */
    suspend fun randomPosts(): ApiResult = get(api("posts/random"))

    suspend fun getPost(postId: String): ApiResult = get(api("posts/$postId"))

    /** 发帖正文是白名单 HTML（由 RichDocument.toHtml() 生成）。 */
    suspend fun createPost(title: String, contentHtml: String, category: String): ApiResult {
        val body = JSONObject()
            .put("title", title.trim())
            .put("content", contentHtml)
            .put("category", category)
        return post(api("posts"), body)
    }

    suspend fun likePost(postId: String): ApiResult = post(api("posts/$postId/like"))

    suspend fun favoritePost(postId: String): ApiResult = post(api("posts/$postId/favorite"))

    suspend fun deletePost(postId: String): ApiResult = post(api("posts/$postId/delete"))

    // ────────────────── 评论 ──────────────────

    suspend fun comments(postId: String, page: Int = 1, pageSize: Int = 50): ApiResult =
        get(api("posts/$postId/comments"), mapOf("page" to page, "page_size" to pageSize))

    /** 评论正文同样是白名单 HTML；ov2 对评论启用 ALTCHA。 */
    suspend fun createComment(
        postId: String,
        contentHtml: String,
        parentId: String? = null,
    ): ApiResult {
        val body = JSONObject().put("content", contentHtml)
        if (!parentId.isNullOrBlank()) body.put("parent_id", parentId)
        return request("POST", api("posts/$postId/comments"), json = body, captcha = true)
    }

    suspend fun deleteComment(commentId: String): ApiResult = delete(api("comments/$commentId"))

    /** 点赞 / 取消点赞评论；返回 `{success, liked, likes}`。 */
    suspend fun likeComment(commentId: String): ApiResult = post(api("comments/$commentId/like"))

    // ────────────────── 搜索 ──────────────────

    suspend fun search(
        keyword: String,
        page: Int = 1,
        pageSize: Int = Constants.PAGE_SIZE,
        type: String = "both",
    ): ApiResult = get(
        api("search"),
        mapOf("k" to keyword, "page" to page, "page_size" to pageSize, "type" to type),
    )

    // ────────────────── 用户 ──────────────────

    suspend fun userInfo(userId: String): ApiResult = get(api("users/$userId"))

    suspend fun follow(userId: String): ApiResult = post(api("users/$userId/follow"))

    suspend fun userPosts(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get(api("users/$userId/posts"), mapOf("page" to page, "page_size" to pageSize))

    suspend fun userFavorites(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get(api("users/$userId/favorites"), mapOf("page" to page, "page_size" to pageSize))

    suspend fun userComments(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get(api("users/$userId/comments"), mapOf("page" to page, "page_size" to pageSize))

    suspend fun following(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get(api("users/$userId/following"), mapOf("page" to page, "page_size" to pageSize))

    suspend fun followers(userId: String, page: Int = 1, pageSize: Int = Constants.PAGE_SIZE): ApiResult =
        get(api("users/$userId/followers"), mapOf("page" to page, "page_size" to pageSize))

    // ────────────────── 世界频道 ──────────────────

    /** ov2 返回 `{success, items, has_more, next_before_id}`（默认降序）。 */
    suspend fun worldAll(limit: Int = Constants.WORLD_LIMIT, beforeId: Long? = null): ApiResult =
        get(
            api("world/messages"),
            mapOf("limit" to limit, "before_id" to beforeId),
        )

    /** 世界频道正文是 HTML（服务端禁引用卡片、最多 9 图）。 */
    suspend fun worldSend(contentHtml: String, parentId: Long? = null): ApiResult {
        val body = JSONObject().put("content_html", contentHtml)
        if (parentId != null && parentId > 0) body.put("parent_id", parentId)
        return post(api("world/messages"), body)
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
