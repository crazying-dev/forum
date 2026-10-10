package top.crazying.forum.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import top.crazying.forum.ui.screens.FeedStateStore
import top.crazying.forum.ui.screens.needReload

/**
 * 列表页「返回后保留浏览位置」的保留判定（[needReload]）与状态仓库（[FeedStateStore]）。
 *
 * 回归目标：从帖子详情返回列表页时，列表内容与滚动位置必须还在。
 * 只要内容标识（信息流 / 分类 / 搜索词 / 用户 tab）没变，就不应重新加载。
 * 全程不发起网络请求，也不触碰 Android / org.json。
 */
class FeedStateTest {

    @Test
    fun firstLoadIsNeeded() {
        assertTrue(needReload(null, "latest|"))
    }

    @Test
    fun sameContentKeyDoesNotReload() {
        // 从帖子详情返回：loadedKey 与当前标识一致 → 复用，不重载
        assertFalse(needReload("latest|", "latest|"))
    }

    @Test
    fun switchingFeedReloads() {
        assertTrue(needReload("latest|", "comprehensive|"))
    }

    @Test
    fun switchingCategoryReloads() {
        assertTrue(needReload("general", "creative"))
    }

    @Test
    fun loginChangeReloads() {
        assertTrue(needReload("favorites|", "favorites|HG0001"))
    }

    @Test
    fun storeReturnsSameInstanceForKey() {
        val store = FeedStateStore()
        val home = store.feed("home", "latest")
        home.page = 3
        assertSame(home, store.feed("home", "latest"))
        assertEquals(3, store.feed("home", "latest").page)
    }

    @Test
    fun storeSeparatesDifferentKeys() {
        val store = FeedStateStore()
        store.feed("home").page = 2
        store.feed("forum").page = 5
        assertEquals(2, store.feed("home").page)
        assertEquals(5, store.feed("forum").page)
    }

    @Test
    fun userStoreKeepsLoadedTab() {
        val store = FeedStateStore()
        val st = store.user("HG1")
        st.tab = "favorites"
        st.loadedTab = "favorites"
        assertSame(st, store.user("HG1"))
        assertEquals("favorites", store.user("HG1").loadedTab)
        // 返回时 tab 未变 → 不重载
        assertFalse(needReload(store.user("HG1").loadedTab, store.user("HG1").tab))
    }

    @Test
    fun searchStoreKeepsKeywordAndResult() {
        val store = FeedStateStore()
        val s = store.search("幽幽")
        s.searched = true
        assertEquals("幽幽", s.keyword)
        assertSame(s, store.search("幽幽"))
    }

    @Test
    fun defaultFilterIsAppliedOnlyWhenCreating() {
        val store = FeedStateStore()
        assertEquals("latest", store.feed("home", "latest").filter)
        // 已存在时不再套用默认值（用户已切到别的信息流，不能被打回）
        store.feed("home", "latest").filter = "favorites"
        assertEquals("favorites", store.feed("home", "latest").filter)
    }
}
