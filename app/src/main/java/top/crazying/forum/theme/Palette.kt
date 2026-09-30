package top.crazying.forum.theme

import androidx.compose.ui.graphics.Color

/**
 * 一套色板。
 *
 * 字段与 Web 端 `static/css/main.css` 的 `--color-*` 变量、
 * Windows 端 `app/theme.py` 的 `PALETTES` 一一对应（28 个键）。
 */
data class ForumColors(
    val primary: Color,
    val primaryHover: Color,
    val primaryText: Color,
    val bgBody: Color,
    val bgHeader: Color,
    val bgCard: Color,
    val bgInput: Color,
    val bgHover: Color,
    val bgItemHover: Color,
    val bgItemActive: Color,
    val bgIcon: Color,
    val bgIconHover: Color,
    val bgFooter: Color,
    val bgSecondary: Color,
    val border: Color,
    val borderDivider: Color,
    val borderFocus: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val textLight: Color,
    val textAccent: Color,
    val textMuted: Color,
    val danger: Color,
    val dangerHover: Color,
    val codeBg: Color,
    val markBg: Color,
) {
    /** 是否为深色系（决定状态栏图标明暗）。 */
    val isDark: Boolean
        get() = bgBody.luminanceish() < 0.5f

    private fun Color.luminanceish(): Float =
        0.299f * red + 0.587f * green + 0.114f * blue
}

/** 浅色（默认，与 Web 端 `:root` 一致）。 */
val DAY_COLORS = ForumColors(
    primary = Color(0xFF6A8C89),
    primaryHover = Color(0xFF579491),
    primaryText = Color(0xFFFFFFFF),
    bgBody = Color(0xFFD8E6E4),
    bgHeader = Color(0xFFE6EDEC),
    bgCard = Color(0xFFFFFFFF),
    bgInput = Color(0xFFF9FBFA),
    bgHover = Color(0xFFF0F4F3),
    bgItemHover = Color(0xFFF0F4F3),
    bgItemActive = Color(0xFFE9EEED),
    bgIcon = Color(0xFFE9EEED),
    bgIconHover = Color(0xFFD2DDDB),
    bgFooter = Color(0xFF6A8C89),
    bgSecondary = Color(0xFFFFFFFF),
    border = Color(0xFFE1E8E7),
    borderDivider = Color(0xFFF0F4F3),
    borderFocus = Color(0xFF6A8C89),
    textPrimary = Color(0xFF1A2423),
    textSecondary = Color(0xFF2E4659),
    textTertiary = Color(0xFF96A9A7),
    textLight = Color(0xFFE8EEED),
    textAccent = Color(0xFF579491),
    textMuted = Color(0xFF96A9A7),
    danger = Color(0xFFB4544F),
    dangerHover = Color(0xFF9E423D),
    codeBg = Color(0xFFF0F4F3),
    markBg = Color(0xFFFFF3C4),
)

/** 深色（与 Web 端 `.night-mode` 一致）。 */
val NIGHT_COLORS = ForumColors(
    primary = Color(0xFF84A8B9),
    primaryHover = Color(0xFF6A8C89),
    primaryText = Color(0xFF12211F),
    bgBody = Color(0xFF325A64),
    bgHeader = Color(0xFF2F495B),
    bgCard = Color(0xFF1B2726),
    bgInput = Color(0xFF1F2F30),
    bgHover = Color(0xFF2B3A3C),
    bgItemHover = Color(0xFF2B3A3C),
    bgItemActive = Color(0xFF304143),
    bgIcon = Color(0xFF304143),
    bgIconHover = Color(0xFF455A61),
    bgFooter = Color(0xFF2E4659),
    bgSecondary = Color(0xFF1B2726),
    border = Color(0xFF2B3A3C),
    borderDivider = Color(0xFF243435),
    borderFocus = Color(0xFF84A8B9),
    textPrimary = Color(0xFFE8EEED),
    textSecondary = Color(0xFFD8E6E4),
    textTertiary = Color(0xFF84A8B9),
    textLight = Color(0xFFB4D2D8),
    textAccent = Color(0xFFB4D2D8),
    textMuted = Color(0xFF84A8B9),
    danger = Color(0xFFE78284),
    dangerHover = Color(0xFFD06B6D),
    codeBg = Color(0xFF243435),
    markBg = Color(0xFF4A4326),
)

/** 国庆节浅色（暖白/米底 + 中国红主色 + 五星金点缀）。假期外不可手动选中。 */
val NATIONAL_DAY_LIGHT_COLORS = ForumColors(
    primary = Color(0xFFC8102E),
    primaryHover = Color(0xFFA50D24),
    primaryText = Color(0xFFFFFFFF),
    bgBody = Color(0xFFFBF3E6),
    bgHeader = Color(0xFFFEF9EF),
    bgCard = Color(0xFFFFFDF8),
    bgInput = Color(0xFFFFFCF6),
    bgHover = Color(0xFFFBEAE8),
    bgItemHover = Color(0xFFFBEAE8),
    bgItemActive = Color(0xFFF7D9DA),
    bgIcon = Color(0xFFF8E1E0),
    bgIconHover = Color(0xFFF2C4C8),
    bgFooter = Color(0xFFC8102E),
    bgSecondary = Color(0xFFFFFDF8),
    border = Color(0xFFF2CAC5),
    borderDivider = Color(0xFFF6DCD4),
    borderFocus = Color(0xFFC8102E),
    textPrimary = Color(0xFF3A1D1D),
    textSecondary = Color(0xFF7A3226),
    textTertiary = Color(0xFFB49484),
    textLight = Color(0xFFFFF3E0),
    textAccent = Color(0xFFC8102E),
    textMuted = Color(0xFFB49484),
    danger = Color(0xFFB4544F),
    dangerHover = Color(0xFF9E423D),
    codeBg = Color(0xFFF7E9E4),
    markBg = Color(0xFFFFE9A8),
)

/** 国庆节深色（暗红底 + 亮金主色）。假期外不可手动选中。 */
val NATIONAL_DAY_DARK_COLORS = ForumColors(
    primary = Color(0xFFFFD24A),
    primaryHover = Color(0xFFFFC01E),
    primaryText = Color(0xFF3A0D12),
    bgBody = Color(0xFF3A0D12),
    bgHeader = Color(0xFF481015),
    bgCard = Color(0xFF310B10),
    bgInput = Color(0xFF380D12),
    bgHover = Color(0xFF502919),
    bgItemHover = Color(0xFF502919),
    bgItemActive = Color(0xFF5E371D),
    bgIcon = Color(0xFF562F1A),
    bgIconHover = Color(0xFF774F24),
    bgFooter = Color(0xFF4A1219),
    bgSecondary = Color(0xFF310B10),
    border = Color(0xFF5D301C),
    borderDivider = Color(0xFF522519),
    borderFocus = Color(0xFFFFD24A),
    textPrimary = Color(0xFFFFE8C4),
    textSecondary = Color(0xFFF2CF9B),
    textTertiary = Color(0xFFC79A63),
    textLight = Color(0xFFFFD98A),
    textAccent = Color(0xFFFFD24A),
    textMuted = Color(0xFFC79A63),
    danger = Color(0xFFE78284),
    dangerHover = Color(0xFFD06B6D),
    codeBg = Color(0xFF451419),
    markBg = Color(0xFF5C4A18),
)
