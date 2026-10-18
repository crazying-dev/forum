package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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

    // ────────── 结构化双向换算（NewEraDate）──────────

    @Test
    fun gregorianToNewEraIsStructured() {
        val epoch = TimeFmt.gregorianToNewEra(1604)
        assertEquals(1, epoch.yearNum)
        assertFalse(epoch.isBefore)
        assertEquals("无限元年", epoch.label)
        assertEquals("无限元年", epoch.toString())

        val before = TimeFmt.gregorianToNewEra(1603)
        assertEquals(1, before.yearNum)
        assertTrue(before.isBefore)
        assertEquals("无限前1年", before.label)

        assertEquals("无限前104年", TimeFmt.gregorianToNewEra(1500).label)
        assertEquals("无限423年", TimeFmt.gregorianToNewEra(2026).label)
    }

    @Test
    fun newEraToGregorianIsInverse() {
        assertEquals(1604, TimeFmt.newEraToGregorian(1, isBefore = false))
        assertEquals(2026, TimeFmt.newEraToGregorian(423, isBefore = false))
        assertEquals(1603, TimeFmt.newEraToGregorian(1, isBefore = true))
        assertEquals(1500, TimeFmt.newEraToGregorian(104, isBefore = true))
    }

    @Test
    fun newEraToGregorianRejectsZeroAndNegative() {
        assertRejects(0)
        assertRejects(-1)
    }

    @Test
    fun roundTripPreservesGregorianYear() {
        for (g in intArrayOf(1, 1063, 1603, 1604, 1605, 1700, 2026)) {
            val era = TimeFmt.gregorianToNewEra(g)
            assertEquals("公元 $g 年的往返换算不对称", g, TimeFmt.newEraToGregorian(era.yearNum, era.isBefore))
            // 旧接口与新核心必须一致
            if (era.isBefore) {
                assertNull(TimeFmt.wuxianYear(g))
            } else {
                assertEquals(era.yearNum, TimeFmt.wuxianYear(g))
            }
        }
    }

    @Test
    fun ceTextHasNoYearZero() {
        assertEquals("公元 2026 年", TimeFmt.ceText(2026))
        assertEquals("公元前 1 年", TimeFmt.ceText(0))
        assertEquals("公元前 2 年", TimeFmt.ceText(-1))
    }

    // ────────── 公元年输入框：负数 = 公元前（对齐 Web 端口径）──────────

    @Test
    fun ceInputAcceptsBcYears() {
        // 输入 -1 = 公元前 1 年（天文纪年 0）→ 无限前 1604 年
        assertEquals(0, TimeFmt.ceInputToAstronomical(-1))
        val bc1 = TimeFmt.ceInputToNewEra(-1)!!
        assertTrue(bc1.isBefore)
        assertEquals(1604, bc1.yearNum)
        assertEquals("无限前1604年", bc1.label)
        // 公元前 100 年 → 无限前 1703 年
        assertEquals("无限前1703年", TimeFmt.ceInputToNewEra(-100)!!.label)
        // 公元前 M 年 ⇔ 无限前 (1603 + M) 年
        for (m in intArrayOf(1, 100, 1603)) {
            assertEquals(1603 + m, TimeFmt.ceInputToNewEra(-m)!!.yearNum)
        }
    }

    @Test
    fun ceInputRejectsYearZero() {
        assertNull(TimeFmt.ceInputToAstronomical(0))
        assertNull(TimeFmt.ceInputToNewEra(0))
    }

    @Test
    fun ceInputPositiveStaysGregorian() {
        assertEquals(2026, TimeFmt.ceInputToAstronomical(2026))
        assertEquals("无限423年", TimeFmt.ceInputToNewEra(2026)!!.label)
        assertEquals("公元 2026 年", TimeFmt.ceText(TimeFmt.ceInputToAstronomical(2026)!!))
        // 公元前 1604 年（天文纪年 -1603）→ 无限前 3207 年，展示仍为公元前
        assertEquals("无限前3207年", TimeFmt.ceInputToNewEra(-1604)!!.label)
        assertEquals("公元前 1604 年", TimeFmt.ceText(TimeFmt.ceInputToAstronomical(-1604)!!))
    }

    private fun assertRejects(yearNum: Int) {
        var thrown = false
        try {
            TimeFmt.newEraToGregorian(yearNum)
        } catch (e: IllegalArgumentException) {
            thrown = true
        }
        assertTrue("newEraToGregorian($yearNum) 应抛 IllegalArgumentException", thrown)
    }
}
