package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** [takeCodePoints] 的码点截断边界。 */
class TextLimitTest {

    @Test
    fun shortTextIsReturnedAsIs() {
        assertEquals("你好abc", takeCodePoints("你好abc", 10))
        assertEquals("", takeCodePoints("", 10))
    }

    @Test
    fun cutsChineseByCodePoint() {
        assertEquals("你好", takeCodePoints("你好世界", 2))
    }

    @Test
    fun neverSplitsEmojiSurrogatePair() {
        // 每个 emoji 占 2 个 UTF-16 单元；按码点截断后仍是完整 emoji。
        assertEquals("😀", takeCodePoints("😀😀", 1))
        assertEquals("a😀", takeCodePoints("a😀b", 2))
    }

    @Test
    fun nonPositiveLimitReturnsEmpty() {
        assertEquals("", takeCodePoints("abc", 0))
        assertEquals("", takeCodePoints("abc", -1))
    }

    @Test
    fun limitLargerThanTextKeepsAll() {
        val emoji = "😀😀😀"
        assertEquals(emoji, takeCodePoints(emoji, 3))
        assertEquals(emoji, takeCodePoints(emoji, 100))
    }
}
