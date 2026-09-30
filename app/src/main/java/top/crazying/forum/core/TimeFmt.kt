package top.crazying.forum.core

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * 时间与年制。
 *
 * 口径完全对齐 Web 端 `static/js/AfterBody.js` 与 Windows 端 `app/yearmode.py`：
 * * 无限年 = 公元年 − 1604（无限元年 = 公元 1604 年）
 * * 公元年 < 1604 时显示「无限前xxx年」
 * * 后端时间字符串无时区信息时按 **UTC** 解析，再换算到本机时区显示
 */
object TimeFmt {

    /** 带时区信息（Z 或 ±HH:MM / ±HHMM）的 ISO 串。 */
    private val TZ_RE = Regex("[zZ]$|[+-]\\d{2}:?\\d{2}$")
    private val TIME_RE = Regex(":\\d{2}")

    private val PATTERNS = listOf(
        "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss.SSS",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss.SSS",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd",
        "yyyy/MM/dd HH:mm:ss",
    )

    private val UTC: TimeZone = TimeZone.getTimeZone("UTC")

    // ────────────────── 年制 ──────────────────

    fun yearMode(): String = App.yearMode.value

    fun wuxianYear(ce: Int): Int? =
        if (ce < Constants.WUXIAN_EPOCH_CE) null else ce - Constants.WUXIAN_EPOCH_CE

    fun wuxianToCe(wy: Int): String = (wy + Constants.WUXIAN_EPOCH_CE).toString()

    /** 「年」部分（不带「年」字）。 */
    fun yearText(ce: Int, mode: String = yearMode()): String {
        if (mode == Constants.YEAR_MODE_CE) return ce.toString()
        val wy = wuxianYear(ce)
        return if (wy != null) "无限$wy" else "无限前${Constants.WUXIAN_EPOCH_CE - ce}"
    }

    // ────────────────── 解析 ──────────────────

    /** 解析为毫秒时间戳；失败返回 null。无时区信息时按 UTC 处理。 */
    fun parseMillis(t: Any?): Long? {
        val s = t?.toString()?.trim().orEmpty()
        if (s.isEmpty() || s == "null") return null
        var iso = s
        if (!TZ_RE.containsMatchIn(s)) {
            iso = s.replace(' ', 'T')
            if (TIME_RE.containsMatchIn(iso)) iso += "Z"
        }
        for (pattern in PATTERNS) {
            val sdf = SimpleDateFormat(pattern, Locale.US)
            sdf.timeZone = UTC
            sdf.isLenient = false
            try {
                val parsed = sdf.parse(iso) ?: continue
                return parsed.time
            } catch (e: Exception) {
                // 试下一个格式
            }
        }
        return null
    }

    // ────────────────── 格式化 ──────────────────

    /** 相对时间（刚刚 / N 分钟前 / N 小时前），超过 1 天则绝对时间。 */
    fun fmtTime(t: Any?, mode: String = yearMode()): String {
        val ms = parseMillis(t) ?: return t?.toString().orEmpty()
        val diff = (System.currentTimeMillis() - ms) / 1000
        if (diff >= 0 && diff < 60) return "刚刚"
        if (diff >= 0 && diff < 3600) return "${diff / 60} 分钟前"
        if (diff >= 0 && diff < 86400) return "${diff / 3600} 小时前"
        return fmtDateTime(t, mode)
    }

    /** 绝对时间（不做相对化），用于详情页。 */
    fun fmtDateTime(t: Any?, mode: String = yearMode()): String {
        val ms = parseMillis(t) ?: return t?.toString().orEmpty()
        val cal = Calendar.getInstance()
        cal.timeInMillis = ms
        return "%s-%02d-%02d %02d:%02d".format(
            yearText(cal.get(Calendar.YEAR), mode),
            cal.get(Calendar.MONTH) + 1,
            cal.get(Calendar.DAY_OF_MONTH),
            cal.get(Calendar.HOUR_OF_DAY),
            cal.get(Calendar.MINUTE),
        )
    }

    // ────────────────── 生日 ──────────────────

    /** 后端生日整数（如 20120615）→ `YYYY-MM-DD`；不合法返回空串。 */
    fun birthdayValue(age: Any?): String {
        val n = when (age) {
            is Number -> age.toInt()
            else -> age?.toString()?.trim()?.toIntOrNull()
        } ?: return ""
        if (n <= 0) return ""
        val y = n / 10000
        val m = (n / 100) % 100
        val d = n % 100
        if (y < 1000 || m !in 1..12 || d !in 1..31) return ""
        return "%04d-%02d-%02d".format(y, m, d)
    }

    /** 生日展示（年部分跟随年制）。 */
    fun fmtBirthday(age: Any?, mode: String = yearMode()): String {
        val v = birthdayValue(age)
        if (v.isEmpty()) return ""
        val parts = v.split("-")
        if (parts.size != 3) return v
        val y = parts[0].toIntOrNull() ?: return v
        return "${yearText(y, mode)}-${parts[1]}-${parts[2]}"
    }

    /** 由生日算年龄（用于「N 岁」）。 */
    fun ageYears(age: Any?): String {
        val v = birthdayValue(age)
        if (v.isEmpty()) return ""
        val y = v.substring(0, 4).toIntOrNull() ?: return ""
        val m = v.substring(5, 7).toIntOrNull() ?: return ""
        val d = v.substring(8, 10).toIntOrNull() ?: return ""
        val now = Calendar.getInstance()
        var years = now.get(Calendar.YEAR) - y
        val todayMonth = now.get(Calendar.MONTH) + 1
        val todayDay = now.get(Calendar.DAY_OF_MONTH)
        if (todayMonth < m || (todayMonth == m && todayDay < d)) years -= 1
        return if (years in 0..199) years.toString() else ""
    }

    /** HTML 正文 → 纯文本摘要（列表卡片用）。 */
    fun stripHtml(html: String?): String {
        if (html.isNullOrBlank()) return ""
        var t = html
        t = t.replace(Regex("<br\\s*/?>", RegexOption.IGNORE_CASE), " ")
        t = t.replace(Regex("</p>", RegexOption.IGNORE_CASE), " ")
        t = t.replace(Regex("<[^>]+>"), " ")
        t = t.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
        return t.replace(Regex("\\s+"), " ").trim()
    }

    /** 旧接口时间格式备用。 */
    fun nowMillis(): Long = Date().time
}
