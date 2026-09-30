package top.crazying.forum.core

import android.content.Context
import android.content.SharedPreferences

/**
 * 本地持久化（SharedPreferences）。
 *
 * 只存四类东西：主题偏好、年制、用户缓存、Cookie 串；
 * 另加两个更新检查相关的标记（上次检查时间 / 已忽略的版本）。
 * 注意：`themePref` **只允许** day / night / auto 三个基础值，
 * 国庆限定主题是假期内的运行时叠加层，绝不能写进来。
 */
class Prefs(context: Context) {

    private val sp: SharedPreferences =
        context.getSharedPreferences(SP_NAME, Context.MODE_PRIVATE)

    var themePref: String
        get() = sp.getString(KEY_THEME, Constants.THEME_AUTO) ?: Constants.THEME_AUTO
        set(value) = sp.edit().putString(KEY_THEME, value).apply()

    var yearMode: String
        get() = sp.getString(KEY_YEAR, Constants.YEAR_MODE_WUXIAN) ?: Constants.YEAR_MODE_WUXIAN
        set(value) = sp.edit().putString(KEY_YEAR, value).apply()

    /** 用户对象缓存（JSON 字符串），用于冷启动直接渲染头部。 */
    var userJson: String
        get() = sp.getString(KEY_USER, "") ?: ""
        set(value) = sp.edit().putString(KEY_USER, value).apply()

    /** CookieJar 的序列化存储（见 `PrefsCookieJar`）。 */
    var cookieStore: String
        get() = sp.getString(KEY_COOKIES, "") ?: ""
        set(value) = sp.edit().putString(KEY_COOKIES, value).apply()

    /** 上一次登录用的用户名，用于登录页回填。 */
    var lastName: String
        get() = sp.getString(KEY_LAST_NAME, "") ?: ""
        set(value) = sp.edit().putString(KEY_LAST_NAME, value).apply()

    /** 上次自动检查更新的时间戳（毫秒）；0 表示从未检查过。 */
    var lastUpdateCheckAt: Long
        get() = sp.getLong(KEY_UPDATE_CHECK_AT, 0L)
        set(value) = sp.edit().putLong(KEY_UPDATE_CHECK_AT, value).apply()

    /** 用户点过「以后再说」的版本号；同一版本不再自动弹窗。 */
    var updateSkipVersion: String
        get() = sp.getString(KEY_UPDATE_SKIP, "") ?: ""
        set(value) = sp.edit().putString(KEY_UPDATE_SKIP, value).apply()

    /** 退出登录 / 掉线时清理会话（保留主题与年制）。 */
    fun clearSession() {
        sp.edit().remove(KEY_USER).remove(KEY_COOKIES).apply()
    }

    private companion object {
        const val SP_NAME = "forum_prefs"
        const val KEY_THEME = "theme_pref"
        const val KEY_YEAR = "year_mode"
        const val KEY_USER = "user_json"
        const val KEY_COOKIES = "cookie_store"
        const val KEY_LAST_NAME = "last_name"
        const val KEY_UPDATE_CHECK_AT = "update_check_at"
        const val KEY_UPDATE_SKIP = "update_skip_version"
    }
}
