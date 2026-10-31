package top.crazying.forum.core

import org.json.JSONArray
import org.json.JSONObject

/**
 * 发布清单里的单个版本（对应 `/ov2/api/downloads/check` 响应里的 `release` 对象）。
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
    val sizeText: String get() = UpdateParser.humanSize(size)
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
 * 更新清单解析：GitHub Releases（优先）与服务端 `/ov2/api/downloads/check`（兜底）两条线路共用。
 *
 * 本文件刻意保持「纯 Kotlin」：只 import `org.json`，不碰 android / okhttp / BuildConfig，
 * 因此解析逻辑可以直接在 JVM 单测里跑，不需要 Robolectric 或真机。
 */
object UpdateParser {

    /** Android 发布 tag：`Android-V1.2.0`，也容忍 `android-v1.1.9` / `Android-1.2.0` 与预发布后缀。 */
    private val RELEASE_TAG = Regex(
        "^Android-V?(\\d+(?:\\.\\d+)*)(?:-[0-9A-Za-z.-]+)?$",
        RegexOption.IGNORE_CASE,
    )

    /** GitHub asset digest 的前缀（形如 `sha256:abc…`）。 */
    private const val SHA256_PREFIX = "sha256:"

    /** release body 里常见的列表符号。 */
    private val NOTE_PREFIXES = arrayOf("- ", "* ", "• ")

    /**
     * 版本号比较（与服务端 Go `compareVersions` 同口径）。
     *
     * 按 `.` 分段取数字比较，缺段补 0，非法段按 0；
     * a < b 返回 -1，a == b 返回 0，a > b 返回 1。
     */
    fun compareVersions(a: String, b: String): Int {
        val va = versionParts(a)
        val vb = versionParts(b)
        val size = maxOf(va.size, vb.size)
        for (i in 0 until size) {
            val x = va.getOrElse(i) { 0L }
            val y = vb.getOrElse(i) { 0L }
            if (x != y) return if (x < y) -1 else 1
        }
        return 0
    }

    /** "v1.2.3" → [1, 2, 3]；段内只取前导数字，取不到按 0。 */
    private fun versionParts(version: String): List<Long> {
        val text = version.trim().trimStart('v', 'V')
        if (text.isEmpty()) return emptyList()
        return text.split('.').map { segment ->
            segment.takeWhile { it in '0'..'9' }.toLongOrNull() ?: 0L
        }
    }

    /** 把 `/downloads/check` 的 JSON 解析成 [UpdateInfo]；结构不对返回 null。 */
    fun parseServerCheck(current: String, obj: JSONObject?): UpdateInfo? {
        obj ?: return null
        val available = obj.optBoolean("available", false)
        val cur = obj.optString("current", "").ifBlank { current }
        val latest = obj.optString("latest", "").trim()
        // ov2 顶层 mandatory = current < min_version；release 内也有一份，缺省时沿用顶层。
        val release = obj.optJSONObject("release")
            ?.let { parseRelease(it, obj.optBoolean("mandatory", false)) }
        return UpdateInfo(
            available = available,
            current = cur,
            latest = latest,
            message = obj.optString("message", "").trim().ifBlank {
                // ov2 `/downloads/check` 不返回 message：本地兜底一句可直接展示的文案。
                // 有可用更新但清单不完整（release 缺失）时留空，交给弹窗提示「发布信息不完整」。
                when {
                    release != null -> if (latest.isNotEmpty()) "发现新版本 " + latest else "发现新版本"
                    available -> ""
                    cur.isNotEmpty() -> "已是最新版本 " + cur
                    else -> "已是最新版本"
                }
            },
            release = release,
        )
    }

    private fun parseRelease(obj: JSONObject, topMandatory: Boolean = false): UpdateRelease {
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
            mandatory = obj.optBoolean("mandatory", topMandatory),
        )
    }

    /**
     * 解析 GitHub Releases API（`/repos/{owner}/{repo}/releases`）的响应体。
     *
     * 选版规则：跳过 draft，只认 `Android-V<版本>` 的 tag 且必须带 `.apk` 附件；
     * 优先稳定版里的最高版本，没有稳定版才退回预发布的最高版本。
     *
     * @return **null** 表示这条线路不可用（body 为空 / 不是 JSON 数组），由调用方回退服务端；
     *         数组可解析时总是返回结果（没有可用的 Android 版本就是「已是最新」）。
     */
    fun parseGithubReleases(current: String, body: String?): UpdateInfo? {
        body ?: return null
        val arr = try {
            JSONArray(body)
        } catch (e: Exception) {
            return null
        }
        var stable: UpdateRelease? = null
        var prerelease: UpdateRelease? = null
        for (i in 0 until arr.length()) {
            val obj = arr.optJSONObject(i) ?: continue
            // 草稿不对外可见，直接跳过。
            if (obj.optBoolean("draft", false)) continue
            val tag = obj.optString("tag_name", "").trim()
            val version = RELEASE_TAG.matchEntire(tag)?.groupValues?.getOrNull(1) ?: continue
            val asset = firstApkAsset(obj.optJSONArray("assets")) ?: continue
            val release = UpdateRelease(
                version = version,
                url = asset.url,
                filename = asset.name,
                size = asset.size,
                sha256 = asset.sha256,
                notes = parseNotes(obj.optString("body", "")),
                mandatory = false,
            )
            if (obj.optBoolean("prerelease", false)) {
                if (prerelease == null || compareVersions(version, prerelease.version) > 0) {
                    prerelease = release
                }
            } else if (stable == null || compareVersions(version, stable.version) > 0) {
                stable = release
            }
        }
        val best = stable ?: prerelease ?: return upToDate(current)
        val available = compareVersions(best.version, current) > 0
        return UpdateInfo(
            available = available,
            current = current,
            latest = best.version,
            message = if (available) "发现新版本 " + best.version else upToDate(current).message,
            release = if (available) best else null,
        )
    }

    /** 无可用新版本时的统一结果。 */
    private fun upToDate(current: String): UpdateInfo = UpdateInfo(
        available = false,
        current = current,
        latest = "",
        message = if (current.isBlank()) "已是最新版本" else "已是最新版本 " + current,
        release = null,
    )

    /** 附件里挑第一个 `.apk`（忽略大小写）；没有则返回 null。 */
    private fun firstApkAsset(assets: JSONArray?): ApkAsset? {
        assets ?: return null
        for (i in 0 until assets.length()) {
            val asset = assets.optJSONObject(i) ?: continue
            val name = asset.optString("name", "").trim()
            if (!name.endsWith(".apk", ignoreCase = true)) continue
            val digest = asset.optString("digest", "").trim()
            return ApkAsset(
                name = name,
                url = asset.optString("browser_download_url", "").trim(),
                size = asset.optLong("size", 0L),
                // 只认合法的 sha256:<64 位 hex>；其它摘要算法/残缺值当作缺失（下载阶段跳过校验），
                // 否则会把 sha512:... 误当 sha256 用，导致每条线路都“校验不通过”。
                sha256 = normalizeSha256(digest),
            )
        }
        return null
    }

    /** 字节数格式化（与 Web / Windows 端 `human_size` 同口径）。纯函数，JVM 单测可直接调用。 */
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

    /** `sha256:<64 位十六进制>` → 小写 hex；其它（sha512 / md5 / 残缺）→ 空串。 */
    private fun normalizeSha256(digest: String): String {
        if (!digest.startsWith(SHA256_PREFIX, ignoreCase = true)) return ""
        val hex = digest.substring(SHA256_PREFIX.length).trim().lowercase()
        val valid = hex.length == 64 && hex.all { it in '0'..'9' || it in 'a'..'f' }
        return if (valid) hex else ""
    }

    /** release body 按行拆成要点：跳过空行与 `#` 标题行，去掉行首列表符号。 */
    private fun parseNotes(body: String): List<String> {
        val notes = ArrayList<String>()
        for (raw in body.split('\n')) {
            var line = raw.trim()
            if (line.isEmpty() || line.startsWith("#")) continue
            for (prefix in NOTE_PREFIXES) {
                if (line.startsWith(prefix)) {
                    line = line.removePrefix(prefix).trim()
                    break
                }
            }
            if (line.isNotEmpty()) notes.add(line)
        }
        return notes
    }

    /** GitHub release 附件中与下载相关的字段。 */
    private data class ApkAsset(
        val name: String,
        val url: String,
        val size: Long,
        val sha256: String,
    )
}
