package top.crazying.forum.core

import androidx.compose.runtime.mutableStateOf
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.atomic.AtomicBoolean

/** 验证弹窗阶段：空闲 / 求解中 / 失败待决策。 */
enum class Phase { Idle, Solving, Failed }

/** 失败弹窗内的用户决策。 */
enum class Decision { Retry, Cancel }

/**
 * ALTCHA 求解的全局可观察状态，供全屏等待/失败弹窗读取。
 *
 * 求解在后台线程进行；`phase` / `failureMessage` 是普通 Compose state，
 * 写入后由下一次重组读取。取消信号用 [AtomicBoolean]，求解循环每候选检查一次。
 */
object AltchaUi {

    /** 转圈至少展示这么久，避免瞬闪。 */
    private const val MIN_SHOWN_MS = 300L

    /** 失败态等待用户决策的兜底上限：超时按取消处理，避免永久占着 captchaMutex。 */
    private const val FAIL_WAIT_TIMEOUT_MS = 5 * 60_000L

    val phase = mutableStateOf(Phase.Idle)
    val failureMessage = mutableStateOf("")

    private val cancelFlag = AtomicBoolean(false)

    @Volatile private var decision: CompletableDeferred<Decision>? = null
    @Volatile private var shownAtNs = 0L

    /** 开始一轮求解：重置取消态与失败文案，记录展示起点。 */
    fun begin() = startSession()

    /**
     * 失败态点「重试」：先唤醒上一轮 fail()，再立即进入新一轮 Solving。
     *
     * 这样重试后不必等挑战请求返回才切转圈；重试期间点「取消」也不会被下一次
     * begin() 清掉（Cancel 会保留在当前会话里，由求解循环/API 检查）。
     */
    fun retry() {
        if (phase.value != Phase.Failed) return
        val current = decision ?: return
        current.complete(Decision.Retry)
        startSession()
    }

    /**
     * 切到失败态并等待用户选择。
     *
     * 先保证转圈至少展示 [MIN_SHOWN_MS]；期间用户已取消则直接返回 [Decision.Cancel]。
     * 用户 5 分钟不操作按取消处理，避免一直占着 captchaMutex。
     */
    suspend fun fail(message: String): Decision {
        ensureMinimumShown()
        if (cancelFlag.get()) return Decision.Cancel
        val deferred = decision ?: return Decision.Cancel
        failureMessage.value = message
        phase.value = Phase.Failed
        // 取消与 fail 可能在极短时间内并发；若用户在切失败态前后点了取消，
        // 重新收回 Failed，避免失败卡片在取消后闪一下。
        if (cancelFlag.get()) {
            phase.value = Phase.Idle
            return Decision.Cancel
        }
        return withTimeoutOrNull(FAIL_WAIT_TIMEOUT_MS) { deferred.await() } ?: Decision.Cancel
    }

    /** 成功：同样保证最短展示；期间被取消返回 false。 */
    suspend fun finishSuccess(): Boolean {
        ensureMinimumShown()
        return !cancelFlag.get()
    }

    /** 取消：置标志、立即关闭弹窗（不等待最短展示）。 */
    fun cancel() {
        cancelFlag.set(true)
        decision?.complete(Decision.Cancel)
        phase.value = Phase.Idle
    }

    /** 收尾：清理弹窗与 pending 决策，避免协程泄漏。 */
    fun end() {
        decision?.complete(Decision.Cancel)
        decision = null
        failureMessage.value = ""
        phase.value = Phase.Idle
    }

    fun isCancelled(): Boolean = cancelFlag.get()

    private fun startSession() {
        decision?.complete(Decision.Cancel)
        cancelFlag.set(false)
        failureMessage.value = ""
        shownAtNs = System.nanoTime()
        decision = CompletableDeferred()
        phase.value = Phase.Solving
    }

    private suspend fun ensureMinimumShown() {
        val shown = shownAtNs
        if (shown <= 0L) return
        val elapsedMs = (System.nanoTime() - shown) / 1_000_000L
        val remaining = MIN_SHOWN_MS - elapsedMs
        if (remaining > 0L) delay(remaining)
    }
}
