package top.crazying.forum.core

import okhttp3.Interceptor
import okhttp3.Request

/**
 * 全局常量。
 *
 * 与 Web 端 `static/js/AfterBody.js`、Windows 端 `app/constants.py` 保持同一套口径：
 * 服务端地址、国庆假期区间、无限年基准年、帖子分类表。
 */
object Constants {

    /** 服务端根地址（全站 HTTPS，且是客户端唯一出网目标）。 */
    const val BASE_URL = "https://www.yjlt.top"

    /** 客户端版本，与 `app/build.gradle.kts` 的 versionName 保持一致。 */
    const val APP_VERSION = "1.0.14"

    /** 请求 UA，便于服务端日志区分端（服务端最低版本闸门也会回退解析它）。 */
    val CLIENT_UA = "CrForum-Android/" + APP_VERSION

    // ────────────────── 最低版本闸门 ──────────────────
    /**
     * 客户端平台标识。
     *
     * 与 Web（`static/js/AfterBody.js` 的 `web`）、Windows（`app/constants.py`
     * 的 `CLIENT_PLATFORM`）同口径；服务端发布清单里的 `min_versions` 就按它取值。
     */
    const val CLIENT_PLATFORM = "android"

    /**
     * 每个请求都携带的客户端标识头。
     *
     * 服务端读 `X-Client-Platform` + `X-Client-Version`（两者缺失时回退解析
     * `User-Agent: CrForum-Android/<版本>`）；低于清单 `min_versions.android`
     * 时返回 **HTTP 426 + `VERSION_TOO_LOW`**，客户端据此弹出强制更新窗。
     */
    val CLIENT_HEADERS: Map<String, String> = mapOf(
        "X-Client-Platform" to CLIENT_PLATFORM,
        "X-Client-Version" to APP_VERSION,
    )

    /** 最低版本闸门的错误码（与 Web / Windows / 服务端同源）。 */
    const val VERSION_TOO_LOW_CODE = "VERSION_TOO_LOW"

    /**
     * 是否命中「版本过低」闸门：HTTP 426，或响应体 `code` 为 [VERSION_TOO_LOW_CODE]。
     *
     * 服务端两种信号都会给，这里取「或」做双保险。纯函数，便于 JVM 单测。
     */
    fun isVersionTooLow(status: Int, code: String?): Boolean =
        status == 426 || (code ?: "").trim() == VERSION_TOO_LOW_CODE

    /**
     * 给一个请求补上 [CLIENT_HEADERS]（纯函数，不改动入参，便于单测）。
     *
     * `header()` 是「先删后加」，重复调用不会把头叠加成多份。
     */
    fun applyClientHeaders(request: Request): Request {
        val builder = request.newBuilder()
        for ((k, v) in CLIENT_HEADERS) builder.header(k, v)
        return builder.build()
    }

    /**
     * 统一给所有 OkHttp 请求加客户端标识头的拦截器。
     *
     * 挂在请求链最外层后，[Api] 的 `request()` / 头像上传 / `fetchText` 与
     * `Updater` 的下载客户端都会自动携带，无需逐处写 header。
     */
    fun clientHeaderInterceptor(): Interceptor = Interceptor { chain ->
        chain.proceed(applyClientHeaders(chain.request()))
    }

    /** WIKI 页（已改为原生 Compose 渲染，仅 Live2D 子页用 WebView 兜底）。 */
    const val WIKI_PATH = "/WIKI"
    val WIKI_URL = BASE_URL + WIKI_PATH

    /** Live2D 交互模型页（唯一保留 WebView 的页面，已注入样式去掉网页外壳）。 */
    const val LIVE2D_PATH = "/Live2D"
    val LIVE2D_URL = BASE_URL + LIVE2D_PATH

    /** WIKI 静态资源（封面 / 横幅 / 说明文档）。 */
    const val WIKI_IMG_DIR = "/static/img/wiki"
    const val MOUSE_IMG_DIR = "/static/img/mouse/Liunx"
    const val MOUSE_README_PATH = "/static/mouse/Liunx/README.md"

    const val HEALTHZ_PATH = "/healthz"

    // ────────────────── 应用更新 ──────────────────
    /** 与发布清单里的平台 key 一致。 */
    const val PLATFORM_ANDROID = "android"

    /** 版本检查：`GET /api/app/check?platform=android&version=<当前版本>`。 */
    const val CHECK_UPDATE_PATH = "/api/app/check"

    /** 站内反代前缀：`/api/app/mirror/android/<文件名>`（服务器流式转发 GitHub 直链）。 */
    const val MIRROR_PATH = "/api/app/mirror"

    /** 冷启动自动检查的最小间隔：24 小时（手动点「检查更新」不受此限制）。 */
    const val UPDATE_CHECK_INTERVAL_MS = 24L * 60 * 60 * 1000

    /** 安装包存放目录（App 私有缓存，下载后交给系统安装器，装完可丢）。 */
    const val UPDATE_DIR = "updates"

    /** 图片磁盘缓存目录（App 私有缓存；按 24 小时时段分桶，见 `CachePolicy`）。 */
    const val IMAGE_CACHE_DIR = "image_cache"

    /**
     * GitHub 直链的公共加速前缀（与 Windows 端 `constants.ACCELERATOR_MIRRORS` 同源）。
     *
     * Android 端不做 DoH DNS 接管（OkHttp 走系统解析，改造收益不值当），
     * 因此下载回退链是「直连 → 公共加速 → 站内反代」，见 [Updater.downloadAttempts]。
     */
    val ACCELERATOR_MIRRORS = listOf(
        "https://ghproxy.net/",
        "https://gh-proxy.com/",
        "https://ghfast.top/",
    )

    // ────────────────── 彩蛋 ──────────────────
    /** 随机一条彩蛋（服务端从 `EasterEgg/1.json` 抽）。 */
    const val EASTER_EGG_PATH = "/Easter-Egg"

    /** 每日一言（第三方，与网页端 `AfterBody.js` 用的是同一个接口）。 */
    const val SENTENCE_TEXT_URL = "https://dlystc.unknownmp.top/api/v2/sentence/text?format=full"
    const val SENTENCE_JSON_URL = "https://dlystc.unknownmp.top/api/v2/sentence"

    // ────────────────── 赞赏码（常驻入口用） ──────────────────
    // 远端图床地址；“我的”页直接展示，Coil 会自动落盘缓存，无需每次重新下载。
    // 与 Web（base.html 的 data-src）、Windows（app/constants.py PROMO_QR_URL）同源。
    const val REWARD_QR_URL = "https://img.crazying-dev.top/other/help.png"

    // ────────────────── 隐私政策 ──────────────────
    /**
     * 当前隐私政策版本，与 `PrivacyScreen` 正文标题里的「版本」一致。
     *
     * 用户同意后把该值写入 `Prefs.privacyAgreedVersion`；政策版本升号时
     * 会在下次启动重新弹窗征得同意（合规要求）。
     */
    const val PRIVACY_POLICY_VERSION = "2.1"

    // ────────────────── 国庆假期 ──────────────────
    // 本地时间 10-01 00:00 ~ 10-07 24:00（等价于 10-08 00:00 开区间，因此只判 1..7 日）
    const val NATIONAL_DAY_MONTH = 10
    const val NATIONAL_DAY_FROM_DAY = 1
    const val NATIONAL_DAY_TO_DAY = 7

    // ────────────────── 年制 ──────────────────
    /** 无限元年 = 公元年 − 1604（无限元年 = 公元 1604 年）。 */
    const val WUXIAN_EPOCH_CE = 1604
    const val YEAR_MODE_WUXIAN = "wuxian"
    const val YEAR_MODE_CE = "ce"

    // ────────────────── 主题偏好 ──────────────────
    // 只会是这三个「基础值」；国庆浅/深属于假期内的强制叠加层，不进设置、不落盘。
    const val THEME_DAY = "day"
    const val THEME_NIGHT = "night"
    const val THEME_AUTO = "auto"

    // ────────────────── 分页 ──────────────────
    const val PAGE_SIZE = 20
    const val RANDOM_LIMIT = 200
    const val COMPREHENSIVE_LIMIT = 100
    const val WORLD_LIMIT = 100

    // ────────────────── 帖子分类 ──────────────────
    val CATEGORY_ORDER = listOf("general", "talk", "question", "share", "creative")

    private val CATEGORY_LABELS = mapOf(
        "general" to "综合",
        "talk" to "闲聊",
        "question" to "求助",
        "share" to "分享",
        "creative" to "创作",
    )

    fun categoryLabel(key: String?): String {
        val k = (key ?: "").trim()
        if (k.isEmpty()) return "综合"
        return CATEGORY_LABELS[k] ?: k
    }

    /**
     * 相对路径 / 协议相对地址 → 绝对 URL。
     * 服务端历史数据里头像字段三种形式都存在。
     */
    fun absolute(pathOrUrl: String?): String {
        val s = (pathOrUrl ?: "").trim()
        if (s.isEmpty()) return ""
        if (s.startsWith("http://") || s.startsWith("https://")) return s
        if (s.startsWith("//")) return "https:$s"
        if (s.startsWith("/")) return BASE_URL + s
        return "$BASE_URL/$s"
    }
}
