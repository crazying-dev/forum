package top.crazying.forum.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import java.util.Calendar

/**
 * 具体要渲染的主题。
 *
 * `MANUAL` 里的两个值是设置页可见、可手动切换的；
 * 国庆浅/深只在假期内由 [ThemeResolver.resolve] 强制叠加上去，
 * 不出现在设置页、也不写入 SharedPreferences。
 */
enum class ThemeMode(val id: String) {
    DAY("day"),
    NIGHT("night"),
    NATIONAL_LIGHT("national_day_light"),
    NATIONAL_DARK("national_day_dark"),
    ;

    val colors: ForumColors
        get() = when (this) {
            DAY -> DAY_COLORS
            NIGHT -> NIGHT_COLORS
            NATIONAL_LIGHT -> NATIONAL_DAY_LIGHT_COLORS
            NATIONAL_DARK -> NATIONAL_DAY_DARK_COLORS
        }

    companion object {
        /** 设置页里列出的基础选项（对应偏好 day / night / auto）。 */
        val BASE_OPTIONS = listOf(Constants.THEME_DAY, Constants.THEME_NIGHT, Constants.THEME_AUTO)

        fun fromId(id: String?): ThemeMode = when (id) {
            NIGHT.id -> NIGHT
            NATIONAL_LIGHT.id -> NATIONAL_LIGHT
            NATIONAL_DARK.id -> NATIONAL_DARK
            else -> DAY
        }
    }
}

/**
 * 主题解析：把「用户偏好」+「是否假期」解析为具体主题。
 *
 * 国庆假期（本地时间 10-01 00:00 ~ 10-07 24:00）内为**强制叠加层**：
 * * `day`   → 国庆浅色
 * * `night` → 国庆深色
 * * `auto`  → 恒为国庆浅色（假期内不按时间/系统切换）
 *
 * 假期外：`day`→浅色，`night`→深色，`auto`→跟随系统。
 */
object ThemeResolver {

    fun isNationalDay(now: Calendar = Calendar.getInstance()): Boolean {
        val month = now.get(Calendar.MONTH) + 1
        val day = now.get(Calendar.DAY_OF_MONTH)
        return month == Constants.NATIONAL_DAY_MONTH &&
            day >= Constants.NATIONAL_DAY_FROM_DAY &&
            day <= Constants.NATIONAL_DAY_TO_DAY
    }

    fun resolve(
        pref: String,
        systemDark: Boolean,
        now: Calendar = Calendar.getInstance(),
    ): ThemeMode {
        // 已经是国庆具体主题时幂等返回（便于 resolve(resolve(...))）
        if (pref == ThemeMode.NATIONAL_LIGHT.id) return ThemeMode.NATIONAL_LIGHT
        if (pref == ThemeMode.NATIONAL_DARK.id) return ThemeMode.NATIONAL_DARK
        val holiday = isNationalDay(now)
        return when (pref) {
            Constants.THEME_DAY -> if (holiday) ThemeMode.NATIONAL_LIGHT else ThemeMode.DAY
            Constants.THEME_NIGHT -> if (holiday) ThemeMode.NATIONAL_DARK else ThemeMode.NIGHT
            else -> if (holiday) ThemeMode.NATIONAL_LIGHT
            else if (systemDark) ThemeMode.NIGHT else ThemeMode.DAY
        }
    }
}

/** 当前生效的色板，所有页面通过 `ForumTheme.colors` 取色。 */
val LocalForumColors = staticCompositionLocalOf { DAY_COLORS }

object ForumTheme {
    val colors: ForumColors
        @Composable
        @ReadOnlyComposable
        get() = LocalForumColors.current
}

private fun schemeOf(c: ForumColors) = if (c.isDark) darkColorScheme(
    primary = c.primary,
    onPrimary = c.primaryText,
    background = c.bgBody,
    onBackground = c.textPrimary,
    surface = c.bgCard,
    onSurface = c.textPrimary,
    surfaceVariant = c.bgInput,
    onSurfaceVariant = c.textSecondary,
    outline = c.border,
    error = c.danger,
) else lightColorScheme(
    primary = c.primary,
    onPrimary = c.primaryText,
    background = c.bgBody,
    onBackground = c.textPrimary,
    surface = c.bgCard,
    onSurface = c.textPrimary,
    surfaceVariant = c.bgInput,
    onSurfaceVariant = c.textSecondary,
    outline = c.border,
    error = c.danger,
)

/**
 * 主题入口：Compose 全树必须包在它里面。
 *
 * 同时负责同步系统状态栏/导航栏颜色与图标明暗（与 Web 端的 `<meta name="theme-color">` 同义）。
 */
@Composable
fun ForumTheme(content: @Composable () -> Unit) {
    val systemDark = isSystemInDarkTheme()
    val mode = ThemeResolver.resolve(App.themePref.value, systemDark)
    val colors = mode.colors

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            runCatching {
                val window = (view.context as Activity).window
                window.statusBarColor = colors.bgBody.toArgb()
                window.navigationBarColor = colors.bgBody.toArgb()
                val controller = WindowCompat.getInsetsController(window, view)
                controller.isAppearanceLightStatusBars = !colors.isDark
                controller.isAppearanceLightNavigationBars = !colors.isDark
            }
        }
    }

    MaterialTheme(colorScheme = schemeOf(colors)) {
        CompositionLocalProvider(LocalForumColors provides colors, content = content)
    }
}
