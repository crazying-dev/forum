package top.crazying.forum.core

import android.content.Context
import android.content.SharedPreferences

/**
 * 本地持久化（SharedPreferences）。
 *
 * 只存四类东西：主题偏好、年制、用户缓存、Cookie 串。
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
    }
}
