package top.crazying.forum.core

import androidx.compose.runtime.mutableStateOf
import java.util.concurrent.atomic.AtomicBoolean

/**
 * ALTCHA 求解的全局可观察状态，供全屏进度遮罩读取。
 *
 * 求解在后台线程进行，`update()` 只写入普通 Compose state；Compose 会在
 * 下一次重组时读取最新值。取消信号用 [AtomicBoolean]，求解循环每候选检查一次。
 */
object AltchaUi {

    val solving = mutableStateOf(false)
    val progress = mutableStateOf(0f)
    val attempts = mutableStateOf(0L)
    val elapsedMs = mutableStateOf(0L)
    val hint = mutableStateOf("正在完成安全验证…")

    private val cancelFlag = AtomicBoolean(false)

    fun begin(hintText: String = "正在完成安全验证…") {
        cancelFlag.set(false)
        solving.value = true
        progress.value = 0f
        attempts.value = 0L
        elapsedMs.value = 0L
        hint.value = hintText
    }

    fun update(attemptsCount: Long, elapsed: Long, cost: Int) {
        attempts.value = attemptsCount
        elapsedMs.value = elapsed
        // 服务端优先区间是 [cost, 2*cost)，用总数估算进度；最多停在 96%，完成由 end() 归零。
        val expected = (cost.coerceAtLeast(1) * 2L).coerceAtLeast(1L)
        progress.value = (attemptsCount.toFloat() / expected).coerceIn(0f, 0.96f)
    }

    fun end() {
        solving.value = false
        progress.value = 0f
    }

    fun cancel() {
        cancelFlag.set(true)
    }

    fun isCancelled(): Boolean = cancelFlag.get()
}
