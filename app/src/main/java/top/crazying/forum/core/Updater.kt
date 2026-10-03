package top.crazying.forum.core

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import kotlin.coroutines.cancellation.CancellationException
import kotlin.coroutines.coroutineContext

/**
 * 发布清单里的单个版本（对应 `/api/app/check` 响应里的 `release` 对象）。
 *
 * 字段与 Web 端 `app_releases.json` / Windows 端 `app/releases.py` 完全同源。
 */
data class UpdateRelease(
    val version: String,
    val url: String,
    val filename: String,
    val size: Long,
    val sha256: String,
    val notes: List<String>,
    val mandatory: Boolean,
) {

    /** 展示用体积（如 `7.6 MB`）；未知返回空串。 */
    val sizeText: String get() = Updater.humanSize(size)
}

/** 版本检查结果（已解析）。 */
data class UpdateInfo(
    val available: Boolean,
    val current: String,
    val latest: String,
    val message: String,
    val release: UpdateRelease?,
)

/** [Updater.check] 的返回值：成功带数据，失败带一句可直接展示的文案。 */
sealed interface CheckResult {

    data class Success(val info: UpdateInfo) : CheckResult

    data class Failure(val message: String) : CheckResult
}

/**
 * 应用自更新：版本检查 → 三级回退下载 → 体积 / sha256 校验 → 调起系统安装器。
 *
 * 与 Windows 端 `app/updater.py` + `app/netfallback.py` 同思路，差异只有一处：
 * Windows 会在「直连」和「公共加速」之间插一步 *DoH 修复 DNS*，而 Android 走 OkHttp 的
 * 系统 DNS 解析，做单请求 DoH 接管的改造成本远超收益，故有意跳过；
 * 回退链因此是「直连 → 公共加速（ghproxy 系）→ 站内反代」。
 *
 * 下载完成后**一律校验 sha256**，公共镜像即使被篡改也会被直接拒绝。
 */
object Updater {

    /** 下载专用客户端：超时放宽（安装包 ~8MB，弱网下 25s 不够）。 */
    private val downloadClient: OkHttpClient = OkHttpClient.Builder()
        // 同样携带客户端标识头（站内反代与日志都会用到）
        .addInterceptor(Constants.clientHeaderInterceptor())
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    private const val HEX = "0123456789abcdef"

    // ────────────────── 版本检查 ──────────────────

    /** 向服务端要一次版本信息；网络异常 / 响应不可解析都归到 [CheckResult.Failure]。 */
    suspend fun check(api: Api, current: String = Constants.APP_VERSION): CheckResult {
        val result = try {
            api.checkUpdate(current)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return CheckResult.Failure("检查更新失败：" + (e.message ?: "网络异常"))
        }
        if (!result.ok) return CheckResult.Failure(result.message)
        val info = parseCheck(current, result.obj())
            ?: return CheckResult.Failure("检查更新失败：服务端返回格式异常")
        return CheckResult.Success(info)
    }

    /** 冷启动自动检查：距上次检查不足 24 小时则直接跳过。
     *
     * 只把「真正拿到响应」的时刻记入 `prefs.lastUpdateCheckAt`，
     * 失败不占用 24 小时窗口（下次冷启动还会再试）。
     *
     * @return 需要弹窗提示的新版本；无需提示（间隔未到 / 已是最新 / 已被忽略）返回 null。
     */
    suspend fun autoCheck(api: Api): UpdateInfo? {
        val prefs = App.prefs
        val now = System.currentTimeMillis()
        val last = prefs.lastUpdateCheckAt
        if (last > 0L && now - last < Constants.UPDATE_CHECK_INTERVAL_MS) return null
        val outcome = check(api)
        val info = (outcome as? CheckResult.Success)?.info ?: return null
        prefs.lastUpdateCheckAt = now
        if (!info.available) return null
        // 用户点过「以后再说」的版本不再自动打扰（手动检查仍能看到）。
        if (info.latest.isNotEmpty() && info.latest == prefs.updateSkipVersion) return null
        return info
    }

    /** 把 `/api/app/check` 的 JSON 解析成 [UpdateInfo]；结构不对返回 null。 */
    fun parseCheck(current: String, obj: JSONObject?): UpdateInfo? {
        obj ?: return null
        val release = obj.optJSONObject("release")?.let { parseRelease(it) }
        return UpdateInfo(
            available = obj.optBoolean("available", false),
            current = obj.optString("current", "").ifBlank { current },
            latest = obj.optString("latest", "").trim(),
            message = obj.optString("message", "").trim(),
            release = release,
        )
    }

    private fun parseRelease(obj: JSONObject): UpdateRelease {
        val url = obj.optString("url", "").trim()
        val notes = ArrayList<String>()
        obj.optJSONArray("notes")?.let { arr ->
            for (i in 0 until arr.length()) {
                val line = arr.optString(i, "").trim()
                if (line.isNotEmpty()) notes.add(line)
            }
        }
        return UpdateRelease(
            version = obj.optString("version", "").trim(),
            url = url,
            // 清单偶尔只给 url；文件名缺失时从 URL 末段推。
            filename = obj.optString("filename", "").trim()
                .ifBlank { url.substringAfterLast('/').substringBefore('?') },
            size = obj.optLong("size", 0L),
            sha256 = obj.optString("sha256", "").trim(),
            notes = notes,
            mandatory = obj.optBoolean("mandatory", false),
        )
    }

    // ────────────────── 下载回退链 ──────────────────

    /**
     * 构造下载回退列表 → `[(线路标签, 地址)]`，按优先级排列。
     *
     * 非 GitHub 直链不生成任何回退（直连本身就是最终源）。
     */
    fun downloadAttempts(release: UpdateRelease): List<Pair<String, String>> {
        val url = release.url.trim()
        if (url.isEmpty()) return emptyList()
        val attempts = ArrayList<Pair<String, String>>()
        attempts.add("直连" to url)
        if (isGitHubUrl(url)) {
            for (base in Constants.ACCELERATOR_MIRRORS) {
                val trimmed = base.trim()
                if (trimmed.isEmpty()) continue
                val label = trimmed.removePrefix("https://").removePrefix("http://")
                    .trimEnd('/')
                attempts.add("公共加速（$label）" to trimmed.trimEnd('/') + "/" + url)
            }
            val filename = release.filename.trim()
            if (filename.isNotEmpty()) {
                attempts.add(
                    "站内反代" to Constants.BASE_URL + Constants.MIRROR_PATH + "/" +
                        Constants.PLATFORM_ANDROID + "/" + filename
                )
            }
        }
        return attempts
    }

    /** 是否为 GitHub 系直链（只有它才值得回退）。 */
    fun isGitHubUrl(url: String): Boolean {
        val host = url.toHttpUrlOrNull()?.host?.lowercase() ?: return false
        return host == "github.com" || host.endsWith(".github.com") ||
            host == "githubusercontent.com" || host.endsWith(".githubusercontent.com")
    }

    /**
     * 按回退链下载安装包到 App 私有缓存，并校验体积与 sha256。
     *
     * @param onProgress `(已下载字节, 总字节(未知时 <=0), 线路标签)`；会在 IO 线程回调。
     * @throws IOException 所有线路都失败时抛出，message 为最后一次失败原因。
     */
    suspend fun download(
        context: Context,
        release: UpdateRelease,
        onProgress: (Long, Long, String) -> Unit = { _, _, _ -> },
    ): File = withContext(Dispatchers.IO) {
        val attempts = downloadAttempts(release)
        if (attempts.isEmpty()) throw IOException("发布清单里没有可用的下载地址")
        val dir = File(context.cacheDir, Constants.UPDATE_DIR).apply { mkdirs() }
        val name = release.filename.trim()
            .ifBlank { "forum-android-" + release.version + ".apk" }
        val dest = File(dir, name)
        var reason = "下载失败"
        for ((label, url) in attempts) {
            coroutineContext.ensureActive()
            val error = tryOne(url, dest, release, label, onProgress)
            if (error == null) return@withContext dest
            reason = error
        }
        throw IOException(reason)
    }

    /** 单条线路的下载 + 校验：成功返回 null，失败返回可直接拼接的原因。 */
    private fun tryOne(
        url: String,
        dest: File,
        release: UpdateRelease,
        label: String,
        onProgress: (Long, Long, String) -> Unit,
    ): String? {
        try {
            if (dest.exists()) dest.delete()
            val request = Request.Builder()
                .url(url)
                .header("User-Agent", Constants.CLIENT_UA)
                .header("Accept", "application/octet-stream")
                .build()
            downloadClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return "$label 返回 HTTP " + response.code
                }
                val body = response.body ?: return "$label 响应为空"
                val total = body.contentLength().takeIf { it > 0L } ?: release.size
                body.byteStream().use { input ->
                    FileOutputStream(dest).use { output ->
                        val buffer = ByteArray(64 * 1024)
                        var done = 0L
                        while (true) {
                            val n = input.read(buffer)
                            if (n <= 0) break
                            output.write(buffer, 0, n)
                            done += n
                            onProgress(done, total, label)
                        }
                        output.flush()
                    }
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (dest.exists()) dest.delete()
            return "$label 连接失败：" + (e.message ?: e.javaClass.simpleName)
        }
        val length = dest.length()
        if (length <= 0L) {
            dest.delete()
            return "$label 下载内容为空"
        }
        if (release.size > 0L && length != release.size) {
            dest.delete()
            return "$label 体积不符（实际 $length，应为 " + release.size + "）"
        }
        if (release.sha256.isNotEmpty() &&
            !sha256(dest).equals(release.sha256, ignoreCase = true)
        ) {
            dest.delete()
            return "$label sha256 校验不通过"
        }
        return null
    }

    /** 文件 sha256（小写十六进制）。 */
    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n <= 0) break
                digest.update(buffer, 0, n)
            }
        }
        val bytes = digest.digest()
        return buildString(bytes.size * 2) {
            for (b in bytes) {
                val v = b.toInt() and 0xFF
                append(HEX[v ushr 4])
                append(HEX[v and 0x0F])
            }
        }
    }

    // ────────────────── 安装 ──────────────────

    /** 是否已允许「安装未知应用」（Android 8.0 起是按应用授权）。 */
    fun canInstall(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return true
        return context.packageManager.canRequestPackageInstalls()
    }

    /** 跳到本应用的「安装未知应用」授权页。 */
    fun installPermissionIntent(context: Context): Intent = Intent(
        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        Uri.parse("package:" + context.packageName),
    )

    /**
     * 调起系统安装器安装已下载好的 APK。
     *
     * `cacheDir` 不是可导出目录，必须经 FileProvider 换成 `content://` URI
     * 并授予临时读权限，否则系统安装器会报「解析软件包时出现问题」。
     */
    fun installApk(context: Context, file: File) {
        val authority = context.packageName + ".fileprovider"
        val uri = FileProvider.getUriForFile(context, authority, file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    // ────────────────── 杂项 ──────────────────

    /** 字节数格式化（与 Web / Windows 端 `human_size` 同口径）。 */
    fun humanSize(bytes: Long): String {
        if (bytes <= 0L) return ""
        var value = bytes.toDouble()
        val units = arrayOf("B", "KB", "MB", "GB", "TB")
        var index = 0
        while (value >= 1024.0 && index < units.size - 1) {
            value /= 1024.0
            index++
        }
        return if (index == 0) {
            bytes.toString() + " B"
        } else {
            String.format(java.util.Locale.US, "%.1f %s", value, units[index])
        }
    }
}
