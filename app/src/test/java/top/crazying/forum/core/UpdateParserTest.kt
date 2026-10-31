package top.crazying.forum.core

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 更新清单解析的 JVM 单测：GitHub Releases（优先）与服务端 `/downloads/check`（兜底）。
 *
 * [UpdateParser] 只依赖 `org.json`，所以这些用例全部跑在纯 JVM 上，不碰 Android / 网络。
 */
class UpdateParserTest {

    // ────────────────── 测试数据 ──────────────────

    /** GitHub release 里的一个附件；`digest` 传 null 表示字段缺失。 */
    private fun asset(
        name: String,
        url: String = "https://example.com/$name",
        size: Long = 8_000_000L,
        digest: String? = null,
    ): JSONObject {
        val obj = JSONObject()
            .put("name", name)
            .put("size", size)
            .put("browser_download_url", url)
        if (digest != null) obj.put("digest", digest)
        return obj
    }

    /** GitHub Releases API 里的一条 release（只写解析用到的字段）。 */
    private fun release(
        tag: String,
        prerelease: Boolean = false,
        draft: Boolean = false,
        assets: List<JSONObject> = listOf(asset("forum-android.apk")),
        body: String = "",
    ): JSONObject = JSONObject()
        .put("tag_name", tag)
        .put("prerelease", prerelease)
        .put("draft", draft)
        .put("body", body)
        .put("assets", JSONArray(assets))

    private fun parse(vararg releases: JSONObject, current: String = "1.1.0"): UpdateInfo? =
        UpdateParser.parseGithubReleases(current, JSONArray(releases.toList()).toString())

    private fun parseBody(body: String?, current: String = "1.1.0"): UpdateInfo? =
        UpdateParser.parseGithubReleases(current, body)

    // ────────────────── tag 过滤 ──────────────────

    @Test
    fun githubAcceptsOnlyAndroidTags() {
        val info = parse(
            release("Windows-V1.3.19"),
            release("v1.0.0"),
            release("Android-Vfoo"),
            release("Android-V1.2.0"),
        )
        assertNotNull(info)
        assertTrue(info!!.available)
        assertEquals("1.2.0", info.latest)
        assertEquals("发现新版本 1.2.0", info.message)
        assertEquals("1.2.0", info.release?.version)
    }

    @Test
    fun githubAcceptsLowercaseTagAndOptionalV() {
        assertEquals("1.1.9", parse(release("android-v1.1.9"), current = "1.1.0")?.latest)
        assertEquals("1.5.0", parse(release("Android-1.5.0"), current = "1.1.0")?.latest)
    }

    @Test
    fun githubSkipsDraftReleases() {
        val info = parse(
            release("Android-V1.9.0", draft = true),
            release("Android-V1.2.0"),
            current = "1.1.0",
        )
        assertEquals("1.2.0", info?.latest)
    }

    // ────────────────── 选版 ──────────────────

    @Test
    fun githubPrefersStableOverNewerPrerelease() {
        val info = parse(
            release("Android-V1.3.0", prerelease = true),
            release("Android-V1.2.0"),
            current = "1.1.0",
        )
        assertEquals("1.2.0", info?.latest)
        assertTrue(info!!.available)
    }

    @Test
    fun githubFallsBackToPrereleaseWhenNoStable() {
        val info = parse(
            release("Android-V1.2.9", prerelease = true),
            release("Android-V1.3.0", prerelease = true),
            current = "1.2.0",
        )
        assertEquals("1.3.0", info?.latest)
        assertTrue(info!!.available)
    }

    @Test
    fun githubSkipsReleaseWithoutApkAsset() {
        val info = parse(
            release("Android-V1.4.0", assets = listOf(asset("notes.txt"), asset("source.zip"))),
            release("Android-V1.2.0"),
            current = "1.1.0",
        )
        assertEquals("1.2.0", info?.latest)

        val none = parse(
            release("Android-V1.4.0", assets = listOf(asset("notes.txt"))),
            current = "1.1.0",
        )
        assertNotNull(none)
        assertFalse(none!!.available)
        assertEquals("", none.latest)
        assertNull(none.release)
    }

    // ────────────────── 附件字段 ──────────────────

    @Test
    fun githubParsesAssetFieldsAndStripsSha256Prefix() {
        val apkUrl = "https://github.com/yoyo-ouo/yj-forum-ouo/releases/download/Android-V1.2.0/forum-android.apk"
        val hex = "deadbeef".repeat(8) // 64 位十六进制，才是合法的 SHA-256
        val info = parse(
            release(
                "Android-V1.2.0",
                assets = listOf(asset("forum-android.apk", apkUrl, 8_123_456L, "sha256:$hex")),
            ),
            current = "1.1.0",
        )
        val release = info!!.release
        assertNotNull(release)
        assertEquals("1.2.0", release!!.version)
        assertEquals("forum-android.apk", release.filename)
        assertEquals(apkUrl, release.url)
        assertEquals(8_123_456L, release.size)
        assertEquals(hex, release.sha256)
        assertEquals(false, release.mandatory)
    }

    @Test
    fun githubRejectsNonSha256DigestOrMalformedHex() {
        // sha512 / md5 / 残缺值都不能当 sha256 用，否则下载阶段会 100% 校验失败。
        val longHex = "a".repeat(128)
        val sha512 = parse(
            release("Android-V1.2.0", assets = listOf(asset("forum-android.apk", digest = "sha512:" + longHex))),
            current = "1.1.0",
        )!!.release!!
        assertEquals("", sha512.sha256)

        val tooShort = parse(
            release("Android-V1.2.0", assets = listOf(asset("forum-android.apk", digest = "sha256:deadbeef"))),
            current = "1.1.0",
        )!!.release!!
        assertEquals("", tooShort.sha256)

        val nonHex = parse(
            release("Android-V1.2.0", assets = listOf(asset("forum-android.apk", digest = "sha256:" + "z".repeat(64)))),
            current = "1.1.0",
        )!!.release!!
        assertEquals("", nonHex.sha256)
    }

    @Test
    fun githubMissingDigestBecomesEmptySha256() {
        val missing = parse(release("Android-V1.2.0"), current = "1.1.0")!!.release!!
        assertEquals("", missing.sha256)

        val nullDigest = parse(
            release("Android-V1.2.0", assets = listOf(asset("forum-android.apk", digest = null))),
            current = "1.1.0",
        )!!.release!!
        assertEquals("", nullDigest.sha256)
    }

    // ────────────────── 版本比较 ──────────────────

    @Test
    fun compareVersionsComparesEachSegmentNumerically() {
        assertTrue(UpdateParser.compareVersions("1.10.0", "1.9.0") > 0)
        assertEquals(0, UpdateParser.compareVersions("2.0", "2.0.0"))
        assertTrue(UpdateParser.compareVersions("1.3", "1.3.18") < 0)
    }

    @Test
    fun compareVersionsToleratesPrefixAndInvalidSegments() {
        assertEquals(0, UpdateParser.compareVersions("v1.2.3", "1.2.3"))
        assertEquals(0, UpdateParser.compareVersions("1.2.x", "1.2.0"))
        assertTrue(UpdateParser.compareVersions("1.2.3", "1.2.10") < 0)
    }

    // ────────────────── notes ──────────────────

    @Test
    fun githubParsesNotesFromReleaseBody() {
        val body = """
            # 更新内容

            - 修复崩溃
            * 新增功能
            • 优化性能
            普通说明
        """.trimIndent()
        val release = parse(release("Android-V1.2.0", body = body), current = "1.1.0")!!.release!!
        assertEquals(listOf("修复崩溃", "新增功能", "优化性能", "普通说明"), release.notes)
    }

    // ────────────────── 已是最新 / 空清单 ──────────────────

    @Test
    fun githubEmptyArrayMeansUpToDate() {
        val info = parseBody("[]", current = "1.1.0")
        assertNotNull(info)
        assertFalse(info!!.available)
        assertEquals("1.1.0", info.current)
        assertEquals("", info.latest)
        assertEquals("已是最新版本 1.1.0", info.message)
        assertNull(info.release)
    }

    @Test
    fun githubOlderReleaseMeansUpToDate() {
        val info = parse(release("Android-V1.1.0"), current = "1.1.0")
        assertNotNull(info)
        assertFalse(info!!.available)
        assertEquals("1.1.0", info.latest)
        assertEquals("已是最新版本 1.1.0", info.message)
        assertNull(info.release)
    }

    // ────────────────── 服务端兜底 ──────────────────

    @Test
    fun serverCheckParsesLegacyStructure() {
        val obj = JSONObject(
            """
            {
              "available": true,
              "mandatory": false,
              "current": "1.0.0",
              "latest": "1.2.0",
              "release": {
                "version": "1.2.0",
                "url": "https://example.com/forum-android-1.2.0.apk",
                "filename": "forum-android-1.2.0.apk",
                "size": 8123456,
                "sha256": "deadbeef",
                "notes": ["修复崩溃", "新增功能"],
                "mandatory": false
              }
            }
            """.trimIndent(),
        )
        val info = UpdateParser.parseServerCheck("1.1.0", obj)
        assertNotNull(info)
        assertTrue(info!!.available)
        assertEquals("1.0.0", info.current)
        assertEquals("1.2.0", info.latest)
        assertEquals("发现新版本 1.2.0", info.message)
        val release = info.release
        assertNotNull(release)
        assertEquals("1.2.0", release!!.version)
        assertEquals("forum-android-1.2.0.apk", release.filename)
        assertEquals(8_123_456L, release.size)
        assertEquals("deadbeef", release.sha256)
        assertEquals(listOf("修复崩溃", "新增功能"), release.notes)
        assertFalse(release.mandatory)
    }

    @Test
    fun serverCheckKeepsExplicitMessageAndFallsBackToTopMandatory() {
        val obj = JSONObject()
            .put("available", true)
            .put("mandatory", true)
            .put("current", "1.0.0")
            .put("latest", "1.2.0")
            .put("message", " 服务端文案 ")
            // 只给 url：文件名从 URL 末段推，mandatory 缺省沿用顶层。
            .put("release", JSONObject().put("version", "1.2.0").put("url", "https://example.com/app.apk"))
        val info = UpdateParser.parseServerCheck("1.0.0", obj)!!
        assertEquals("服务端文案", info.message)
        assertEquals("app.apk", info.release!!.filename)
        assertTrue(info.release!!.mandatory)
    }

    @Test
    fun serverCheckHandlesUpToDateResponse() {
        val obj = JSONObject()
            .put("available", false)
            .put("current", "1.1.0")
            .put("latest", "1.1.0")
        val info = UpdateParser.parseServerCheck("1.0.0", obj)!!
        assertFalse(info.available)
        assertEquals("1.1.0", info.current)
        assertNull(info.release)
        assertEquals("已是最新版本 1.1.0", info.message)
    }

    // ────────────────── 畸形输入 ──────────────────

    @Test
    fun malformedGithubBodyReturnsNull() {
        assertNull(parseBody(null))
        assertNull(parseBody("not-json"))
        // 不是数组（比如 GitHub 的错误对象）也当作线路不可用。
        assertNull(parseBody("{\"message\":\"API rate limit exceeded\"}"))
    }

    @Test
    fun malformedServerCheckReturnsNull() {
        assertNull(UpdateParser.parseServerCheck("1.1.0", null))
    }
}
