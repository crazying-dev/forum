package top.crazying.forum.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [AltchaUi] 的决策逻辑：最短转圈展示、失败重试/取消、取消立即收尾。
 *
 * 不依赖 Android 环境（Compose `mutableStateOf` 在 JVM 单测可用）；时间断言留 20ms 余量。
 */
class AltchaUiTest {

    @After
    fun tearDown() {
        AltchaUi.end()
    }

    @Test
    fun begin_entersSolvingAndClearsFailure() {
        AltchaUi.begin()
        assertEquals(Phase.Solving, AltchaUi.phase.value)
        assertEquals("", AltchaUi.failureMessage.value)
        assertFalse(AltchaUi.isCancelled())
    }

    @Test
    fun fail_waitsMinThenRetryStartsNewSession() = runBlocking {
        AltchaUi.begin()
        val started = System.currentTimeMillis()
        val pending = async(Dispatchers.Default) { AltchaUi.fail("boom") }
        // 等 fail() 真正进入 Failed（最短展示 300ms）后再点重试。
        delay(350)
        AltchaUi.retry()

        assertEquals(Decision.Retry, pending.await())
        assertTrue(
            "最短展示未生效：${System.currentTimeMillis() - started}ms",
            System.currentTimeMillis() - started >= 280,
        )
        // retry() 会立刻开启新一轮 Solving 并清空失败文案。
        assertEquals(Phase.Solving, AltchaUi.phase.value)
        assertEquals("", AltchaUi.failureMessage.value)
    }

    @Test
    fun retry_startsNewSessionAndCancelStaysCancelled() = runBlocking {
        AltchaUi.begin()
        val first = async(Dispatchers.Default) { AltchaUi.fail("a") }
        delay(350)
        AltchaUi.retry()
        assertEquals(Decision.Retry, first.await())
        assertEquals(Phase.Solving, AltchaUi.phase.value)

        AltchaUi.cancel()
        assertEquals(Phase.Idle, AltchaUi.phase.value)
        assertTrue(AltchaUi.isCancelled())
        assertFalse(AltchaUi.finishSuccess())
    }

    @Test
    fun retry_createsFreshDecision() = runBlocking {
        AltchaUi.begin()
        val first = async(Dispatchers.Default) { AltchaUi.fail("a") }
        delay(350)
        AltchaUi.retry()
        first.await()

        // retry 之后必须换新的 deferred；否则第二轮的 fail 会复用已完成的
        // deferred 并立刻返回 Retry，造成无用户交互的自旋。
        val second = async(Dispatchers.Default) { AltchaUi.fail("b") }
        delay(350)
        assertFalse("retry 后 fail 不应立即完成", second.isCompleted)
        AltchaUi.cancel()
        assertEquals(Decision.Cancel, second.await())
    }

    @Test
    fun cancel_closesImmediatelyAndFailsToCancel() = runBlocking {
        AltchaUi.begin()
        val pending = async(Dispatchers.Default) { AltchaUi.fail("boom") }
        delay(30)
        AltchaUi.cancel()

        assertEquals(Phase.Idle, AltchaUi.phase.value)
        assertTrue(AltchaUi.isCancelled())
        assertEquals(Decision.Cancel, pending.await())
    }

    @Test
    fun finishSuccess_enforcesMinimumShownAndHonorsCancel() = runBlocking {
        AltchaUi.begin()
        val started = System.currentTimeMillis()
        assertTrue(AltchaUi.finishSuccess())
        assertTrue(
            "最短展示未生效：${System.currentTimeMillis() - started}ms",
            System.currentTimeMillis() - started >= 280,
        )

        AltchaUi.begin()
        AltchaUi.cancel()
        assertFalse(AltchaUi.finishSuccess())
    }
}
