package top.crazying.forum.core

import android.content.Context
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import org.json.JSONObject

/**
 * 进程级单例：持有 SharedPreferences、HTTP 客户端，以及「可被 Compose 观察」的会话/设置状态。
 *
 * 由 `ForumApp.onCreate` 调用 [init]，之后全局可用（`App.themePref.value` 等会直接触发重组）。
 */
object App {

    lateinit var prefs: Prefs
        private set

    lateinit var api: Api
        private set

    /** 当前登录用户（服务端返回的 `user` 对象）；null 表示未登录。 */
    val user: MutableState<JSONObject?> = mutableStateOf(null)

    /** 主题偏好：day / night / auto（国庆主题由 ThemeResolver 在假期内强制叠加）。 */
    val themePref: MutableState<String> = mutableStateOf(Constants.THEME_AUTO)

    /** 年制：wuxian（无限年，默认）/ ce（公元年）。 */
    val yearMode: MutableState<String> = mutableStateOf(Constants.YEAR_MODE_WUXIAN)

    /**
     * 发现的新版本（由 [Updater.check] 写入）。
     *
     * 非空时 `ForumRoot` 弹出更新对话框；用户点「以后再说」后写回 null，
     * 同时把版本号记入 `prefs.updateSkipVersion`，避免同一版本反复打扰。
     */
    val updateInfo: MutableState<UpdateInfo?> = mutableStateOf(null)

    /**
     * 服务端判定「客户端版本过低」时写入（HTTP 426 / `VERSION_TOO_LOW`）。
     *
     * 非空时 `ForumRoot` 弹出**不可关闭**的强制更新窗，只有「去更新」与「退出应用」
     * 两个出口；只认第一个命中响应，避免并发请求把弹窗叠成一摞。
     */
    val versionGate: MutableState<VersionGate?> = mutableStateOf(null)

    fun init(context: Context) {
        prefs = Prefs(context.applicationContext)
        api = Api(prefs)
        themePref.value = prefs.themePref
        yearMode.value = prefs.yearMode
        val cached = prefs.userJson
        user.value = if (cached.isBlank()) null
        else runCatching { JSONObject(cached) }.getOrNull()
    }

    val isLoggedIn: Boolean
        get() = user.value != null

    /** 当前登录用户的 id（未登录时空串）。 */
    val userId: String
        get() = user.value?.optString("id", "") ?: ""

    fun setUser(obj: JSONObject?) {
        user.value = if (obj == null || obj.length() == 0) null else obj
        prefs.saveUserJson(user.value?.toString() ?: "")
    }

    /**
     * 本地用户缓存是否已超过 24 小时（V1.0.10，见 [CachePolicy]）。
     *
     * 过期不影响使用：`App.init` 仍会先用旧数据渲染头部，随后由 `ForumRoot`
     * 静默刷新覆盖；刷新失败保留旧数据（离线仍可见）。
     */
    val userCacheStale: Boolean
        get() = prefs.userJson.isNotBlank() && CachePolicy.isStale(prefs.userJsonSavedAt)

    fun setThemePref(value: String) {
        val v = if (value == Constants.THEME_NIGHT || value == Constants.THEME_DAY) value
        else Constants.THEME_AUTO
        themePref.value = v
        prefs.themePref = v
    }

    fun setYearMode(value: String) {
        val v = if (value == Constants.YEAR_MODE_CE) Constants.YEAR_MODE_CE
        else Constants.YEAR_MODE_WUXIAN
        yearMode.value = v
        prefs.yearMode = v
    }

    /** 服务端返回 426 / `VERSION_TOO_LOW` 时调用：只处理第一个，之后入参直接丢弃。 */
    fun onVersionTooLow(payload: JSONObject?) {
        if (versionGate.value != null) return
        versionGate.value = VersionGate.from(payload)
    }

    /** 服务端返回 401 时调用：清本地会话，不弹错（避免首次启动未登录就误报）。 */
    fun onUnauthorized() {
        if (user.value == null && prefs.cookieStore.isEmpty()) return
        user.value = null
        prefs.clearSession()
        runCatching { api.clearCookies() }
    }

    fun logoutLocal() {
        user.value = null
        prefs.clearSession()
        runCatching { api.clearCookies() }
    }
}

/**
 * 「版本过低」闸门状态：服务端 426 响应里给出的最低版本、下载地址与提示文案。
 *
 * 对应服务端 `{"success":false,"code":"VERSION_TOO_LOW","message":"版本过低，请更新",
 * "min_version":"…","download_url":"…"}`。
 */
data class VersionGate(
    val minVersion: String,
    val downloadUrl: String,
    val message: String,
) {
    companion object {
        /** 从响应体解析；字段缺失时给出兜底文案，保证弹窗永远有话说。 */
        fun from(payload: JSONObject?): VersionGate = VersionGate(
            minVersion = payload?.optString("min_version", "")?.trim().orEmpty(),
            downloadUrl = payload?.optString("download_url", "")?.trim().orEmpty(),
            message = payload?.optString("message", "")?.trim().orEmpty()
                .ifBlank { "版本过低，请更新" },
        )
    }
}
