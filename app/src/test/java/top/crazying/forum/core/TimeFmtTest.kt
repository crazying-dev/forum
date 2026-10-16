package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 年制换算回归用例（对齐 Web `static/js/AfterBody.js` 与 Windows `app/yearmode.py`）。
 *
 * 回归目标：Android 端曾用 0 起算口径（`ce - 1604`），导致公元 1604 年显示为
 * 「无限0年」、公元 2026 年显示为「无限422」。
 * 正确口径：无限年 **1 起算**，无限 N 年 = 公元 (1603 + N) 年。
 */
class TimeFmtTest {

    @Test
    fun epochYearIsFirstYear() {
        assertEquals(1, TimeFmt.wuxianYear(1604))
    }

    @Test
    fun beforeEpochHasNoWuxianYear() {
        assertNull(TimeFmt.wuxianYear(1603))
        assertNull(TimeFmt.wuxianYear(1))
    }

    @Test
    fun wuxianYearIsOneBased() {
        assertEquals(423, TimeFmt.wuxianYear(2026))
    }

    @Test
    fun yearTextEpochIsYuanNian() {
        assertEquals("无限元年", TimeFmt.yearText(1604, Constants.YEAR_MODE_WUXIAN))
    }

    @Test
    fun yearTextNeverEmitsZero() {
        // 公元 1603 → 无限前 1；公元 1 → 无限前 1603（不存在无限 0 年）
        assertEquals("无限前1", TimeFmt.yearText(1603, Constants.YEAR_MODE_WUXIAN))
        assertEquals("无限前1603", TimeFmt.yearText(1, Constants.YEAR_MODE_WUXIAN))
    }

    @Test
    fun yearTextModernYear() {
        assertEquals("无限423", TimeFmt.yearText(2026, Constants.YEAR_MODE_WUXIAN))
    }

    @Test
    fun yearTextCeModePassesThrough() {
        assertEquals("2026", TimeFmt.yearText(2026, Constants.YEAR_MODE_CE))
        assertEquals("1604", TimeFmt.yearText(1604, Constants.YEAR_MODE_CE))
    }

    @Test
    fun wuxianToCeRoundTrips() {
        assertEquals("1604", TimeFmt.wuxianToCe(1))
        assertEquals("2026", TimeFmt.wuxianToCe(423))
        assertEquals("1603", TimeFmt.wuxianToCe(-1))
    }

    @Test
    fun wuxianToCeZeroDoesNotExist() {
        assertEquals("", TimeFmt.wuxianToCe(0))
    }

    @Test
    fun fmtDateTimeCarriesCorrectYear() {
        val s = TimeFmt.fmtDateTime("2026-05-06T12:30:00Z", Constants.YEAR_MODE_WUXIAN)
        assertTrue("年部分应为「无限423」但实际为：$s", s.startsWith("无限423-"))
    }
}
