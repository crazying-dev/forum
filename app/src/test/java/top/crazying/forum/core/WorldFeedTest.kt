package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 世界频道展示顺序（[WorldFeed]）用例。
 *
 * 回归目标：服务端是倒序返回，界面必须**最新在下**（早的在上）。
 * 之前客户端原样渲染，导致新消息跑到最上面。
 */
class WorldFeedTest {

    @Test
    fun newestBecomesLast() {
        // 服务端顺序：新 → 旧
        val desc = listOf("新", "中", "旧")
        assertEquals(listOf("旧", "中", "新"), WorldFeed.newestLast(desc, 100))
    }

    @Test
    fun emptyStaysEmpty() {
        assertTrue(WorldFeed.newestLast(emptyList<String>(), 100).isEmpty())
    }

    @Test
    fun singleRowIsUnchanged() {
        assertEquals(listOf(1), WorldFeed.newestLast(listOf(1), 100))
    }

    @Test
    fun limitKeepsTheNewestNotTheOldest() {
        // 倒序列表的**头部**才是新的，截断必须取头部
        val desc = listOf("n1", "n2", "n3", "n4", "n5")
        assertEquals(listOf("n2", "n1"), WorldFeed.newestLast(desc, 2))
    }

    @Test
    fun nonPositiveLimitMeansNoTruncation() {
        val desc = listOf("a", "b", "c")
        assertEquals(listOf("c", "b", "a"), WorldFeed.newestLast(desc, 0))
        assertEquals(listOf("c", "b", "a"), WorldFeed.newestLast(desc, -1))
    }

    @Test
    fun limitLargerThanListKeepsEverything() {
        assertEquals(listOf("b", "a"), WorldFeed.newestLast(listOf("a", "b"), 100))
    }
}
