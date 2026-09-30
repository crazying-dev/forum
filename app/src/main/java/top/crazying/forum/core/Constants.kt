package top.crazying.forum.core

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
    const val APP_VERSION = "1.0.1"

    /** 请求 UA，便于服务端日志区分端。 */
    val CLIENT_UA = "CrForum-Android/" + APP_VERSION

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

    // ────────────────── 赞赏码（常驻入口用） ──────────────────
    // 远端图床地址；“我的”页直接展示，Coil 会自动落盘缓存，无需每次重新下载。
    // 与 Web（base.html 的 data-src）、Windows（app/constants.py PROMO_QR_URL）同源。
    const val REWARD_QR_URL = "https://img.crazying-dev.top/other/help.png"

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
