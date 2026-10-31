package top.crazying.forum.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import okio.ByteString.Companion.encodeUtf8
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.min

/**
 * ALTCHA v2 客户端求解（纯 Kotlin/JVM，可单测）。
 *
 * 服务端 `altcha-lib-go/v2` 的挑战结构：
 * `{parameters:{algorithm,nonce,salt,cost,keyLength,keyPrefix,expiresAt,signature}}`。
 * 客户端从 0 开始扫描 counter，用 PBKDF2 派生 key，直到其十六进制以 `keyPrefix` 开头；
 * 然后把 `{challenge, solution}` 做 Base64 交给 `POST /ov2/api/captcha/verify`。
 *
 * 服务端生成 counter 时取 `[cost, 2*cost)`，因此客户端优先扫这个区间，未命中再回退
 * `[0, cost)`（服务端实现变化时仍能解，只是更慢）。
 */
data class AltchaChallenge(
    val raw: JSONObject,
    val algorithm: String,
    val nonceHex: String,
    val saltHex: String,
    val cost: Int,
    val keyLength: Int,
    val keyPrefixHex: String,
    val expiresAt: Long,
)

data class AltchaSolution(
    val counter: Int,
    val derivedKeyHex: String,
    val timeMs: Long,
)

/** 求解结果：命中 / 超时 / 用户取消 / 扫完未命中。 */
sealed interface SolveOutcome {
    data class Solved(val solution: AltchaSolution) : SolveOutcome
    data object TimedOut : SolveOutcome
    data object Cancelled : SolveOutcome
    data object NoMatch : SolveOutcome
}

object Altcha {

    private const val DEFAULT_COST = 5000
    private const val DEFAULT_KEY_LENGTH = 32
    private const val MAX_COST = 20_000
    private const val MAX_KEY_LENGTH = 64
    private const val MAX_PREFIX_HEX = 128
    private const val MAX_HEX_CHARS = 128
    private const val MAX_WORKERS = 4
    private const val HMAC_SHA256_LEN = 32

    /** 解析服务端返回的 Challenge JSON；结构不合法返回 null。 */
    fun parse(json: JSONObject?): AltchaChallenge? {
        val params = json?.optJSONObject("parameters") ?: return null
        val algorithm = params.optString("algorithm", "").trim()
        val nonce = params.optString("nonce", "").trim()
        val salt = params.optString("salt", "").trim()
        if (algorithm.isEmpty() || nonce.isEmpty() || salt.isEmpty()) return null
        // 服务端字段不可信：影响耗时/缓冲的字段全部设上限，畸形挑战直接拒绝。
        if (nonce.length > MAX_HEX_CHARS || salt.length > MAX_HEX_CHARS) return null
        val cost = params.optInt("cost", DEFAULT_COST)
        if (cost !in 1..MAX_COST) return null
        val keyLength = params.optInt("keyLength", DEFAULT_KEY_LENGTH)
        if (keyLength !in 1..MAX_KEY_LENGTH) return null
        val prefix = params.optString("keyPrefix", "").trim().lowercase()
        if (prefix.isEmpty() || prefix.length > MAX_PREFIX_HEX) return null
        if (prefix.length > keyLength * 2) return null
        val expiresAt = params.optLong("expiresAt", 0L)
        return AltchaChallenge(
            raw = json,
            algorithm = algorithm,
            nonceHex = nonce.lowercase(),
            saltHex = salt.lowercase(),
            cost = cost,
            keyLength = keyLength,
            keyPrefixHex = prefix,
            expiresAt = expiresAt,
        )
    }

    /** 挑战是否已过期（0 表示无期限）。 */
    fun isExpired(challenge: AltchaChallenge, nowMs: Long = System.currentTimeMillis()): Boolean {
        if (challenge.expiresAt <= 0L) return false
        return challenge.expiresAt * 1000L <= nowMs
    }

    /** 默认 worker 数：留一个核给 UI/网络，最多 4 个。 */
    fun defaultWorkers(): Int =
        maxOf(1, minOf(MAX_WORKERS, Runtime.getRuntime().availableProcessors() - 1))

    /**
     * 求解。字节精确的 HMAC-SHA256 PBKDF2，worker 内复用 Mac 与缓冲区。
     *
     * 先扫服务端生成区间 `[cost, 2*cost)`，未命中再回退 `[0, cost)`。
     * 每候选检查取消、deadline 与协程活性；`isCancelled` 为真返回 [SolveOutcome.Cancelled]，
     * deadline 到返回 [SolveOutcome.TimedOut]，两轮扫完仍未命中返回 [SolveOutcome.NoMatch]。
     *
     * @param workers 并发度，钳制在 1..4。
     * @param deadlineMs 总耗时上限（≤ 0 表示不限制）。
     */
    suspend fun solve(
        challenge: AltchaChallenge,
        workers: Int = defaultWorkers(),
        deadlineMs: Long = 90_000L,
        isCancelled: () -> Boolean = { false },
    ): SolveOutcome {
        // 服务端可配置算法；当前生产固定 PBKDF2/SHA-256。
        if (!challenge.algorithm.uppercase().startsWith("PBKDF2/SHA-256")) return SolveOutcome.NoMatch
        val cost = challenge.cost
        val keyLength = challenge.keyLength
        if (cost !in 1..MAX_COST || keyLength !in 1..MAX_KEY_LENGTH) return SolveOutcome.NoMatch
        val nonce = hexDecode(challenge.nonceHex) ?: return SolveOutcome.NoMatch
        val salt = hexDecode(challenge.saltHex) ?: return SolveOutcome.NoMatch
        if (nonce.size > MAX_HEX_CHARS / 2 || salt.size > MAX_HEX_CHARS / 2) return SolveOutcome.NoMatch
        val prefixHex = challenge.keyPrefixHex.trim().lowercase()
        if (prefixHex.isEmpty() || prefixHex.length > keyLength * 2) return SolveOutcome.NoMatch
        val prefixBytes = decodePrefixHead(prefixHex) ?: return SolveOutcome.NoMatch

        val nWorkers = workers.coerceIn(1, MAX_WORKERS)
        val startedMs = System.currentTimeMillis()
        val startedNs = System.nanoTime()
        val deadlineNs = if (deadlineMs <= 0L) Long.MAX_VALUE else
            startedNs + deadlineMs * 1_000_000L
        val found = AtomicReference<AltchaSolution?>(null)
        val cancelled = AtomicBoolean(false)
        val timedOut = AtomicBoolean(false)
        val dispatcher = Dispatchers.Default.limitedParallelism(nWorkers)

        /** 分片扫描；每个 worker 只建一套 Mac/缓冲区，之后逐候选复用。 */
        suspend fun scan(from: Int, until: Int) {
            if (from >= until || found.get() != null) return
            coroutineScope {
                (0 until nWorkers).map { index ->
                    async(dispatcher) {
                        val mac = Mac.getInstance("HmacSHA256")
                        val password = ByteArray(nonce.size + 4)
                        System.arraycopy(nonce, 0, password, 0, nonce.size)
                        val block = ByteArray(salt.size + 4)
                        val u = ByteArray(HMAC_SHA256_LEN)
                        val u2 = ByteArray(HMAC_SHA256_LEN)
                        val t = ByteArray(HMAC_SHA256_LEN)
                        val out = ByteArray(keyLength)

                        var n = from + index
                        while (n < until) {
                            if (found.get() != null) return@async
                            if (isCancelled()) {
                                cancelled.set(true)
                                return@async
                            }
                            if (System.nanoTime() >= deadlineNs) {
                                timedOut.set(true)
                                return@async
                            }
                            currentCoroutineContext().ensureActive()

                            putCounterBigEndian(password, nonce.size, n)
                            pbkdf2HmacSha256Into(
                                mac = mac,
                                password = password,
                                salt = salt,
                                iterations = cost,
                                keyLength = keyLength,
                                block = block,
                                u = u,
                                u2 = u2,
                                t = t,
                                out = out,
                            )
                            if (prefixMatches(prefixHex, prefixBytes, out)) {
                                val elapsed = System.currentTimeMillis() - startedMs
                                found.compareAndSet(
                                    null,
                                    AltchaSolution(maxOf(0, n), hexEncode(out.copyOf()), elapsed),
                                )
                                return@async
                            }
                            n += nWorkers
                        }
                    }
                }.awaitAll()
            }
        }

        // 1) 服务端生成区间；2) 回退全量低区间。用 Long 防 cost*2 溢出。
        val firstEnd = min(cost.toLong() * 2L, Int.MAX_VALUE.toLong() - 1L).toInt()
        scan(cost, firstEnd)
        if (found.get() == null && !cancelled.get() && !timedOut.get()) {
            scan(0, cost)
        }

        val solution = found.get()
        if (solution != null) return SolveOutcome.Solved(solution)
        return when {
            cancelled.get() -> SolveOutcome.Cancelled
            timedOut.get() -> SolveOutcome.TimedOut
            else -> SolveOutcome.NoMatch
        }
    }

    /** 构造服务端可校验的 Base64 payload。 */
    fun payload(challenge: AltchaChallenge, solution: AltchaSolution): String {
        val root = JSONObject()
            .put("challenge", challenge.raw)
            .put(
                "solution",
                JSONObject()
                    .put("counter", solution.counter)
                    .put("derivedKey", solution.derivedKeyHex)
                    .put("time", solution.timeMs),
            )
        return root.toString().encodeUtf8().base64()
    }

    /**
     * PBKDF2-HMAC-SHA256 写入调用方提供的缓冲区（无逐候选分配）。
     *
     * 内部用 `mac.init(SecretKeySpec(password, "HmacSHA256"))` 初始化：这是字节精确路径，
     * 不能换成 SecretKeyFactory/PBEKeySpec（会把 nonce 随机字节按 UTF-8 重编码）。
     * `block` 至少 `salt.size + 4`，`u` / `u2` / `t` 至少 `mac.macLength`，`out` 至少 `keyLength`。
     */
    fun pbkdf2HmacSha256Into(
        mac: Mac,
        password: ByteArray,
        salt: ByteArray,
        iterations: Int,
        keyLength: Int,
        block: ByteArray,
        u: ByteArray,
        u2: ByteArray,
        t: ByteArray,
        out: ByteArray,
    ) {
        require(iterations > 0) { "iterations must be > 0" }
        require(keyLength in 1..out.size) { "keyLength must be in 1..out.size" }
        require(block.size >= salt.size + 4) { "block buffer too small" }
        val hLen = mac.macLength
        require(u.size >= hLen && u2.size >= hLen && t.size >= hLen) { "u/u2/t buffer too small" }

        mac.init(SecretKeySpec(password, "HmacSHA256"))
        System.arraycopy(salt, 0, block, 0, salt.size)
        var offset = 0
        var blockIndex = 1
        while (offset < keyLength) {
            block[salt.size] = (blockIndex ushr 24).toByte()
            block[salt.size + 1] = (blockIndex ushr 16).toByte()
            block[salt.size + 2] = (blockIndex ushr 8).toByte()
            block[salt.size + 3] = blockIndex.toByte()

            mac.update(block)
            mac.doFinal(u, 0)
            System.arraycopy(u, 0, t, 0, hLen)
            var src = u
            var dst = u2
            var i = 1
            while (i < iterations) {
                mac.update(src, 0, hLen)
                mac.doFinal(dst, 0)
                for (j in 0 until hLen) {
                    t[j] = (t[j].toInt() xor dst[j].toInt()).toByte()
                }
                val swap = src
                src = dst
                dst = swap
                i++
            }

            val take = min(hLen, keyLength - offset)
            System.arraycopy(t, 0, out, offset, take)
            offset += take
            blockIndex++
        }
    }

    /** PBKDF2-HMAC-SHA256（单块/多块通用，兼容包装；会临时分配 Mac 与缓冲）。 */
    fun pbkdf2HmacSha256(
        password: ByteArray,
        salt: ByteArray,
        iterations: Int,
        keyLength: Int,
    ): ByteArray {
        require(iterations > 0) { "iterations must be > 0" }
        require(keyLength > 0) { "keyLength must be > 0" }
        val mac = Mac.getInstance("HmacSHA256")
        val hLen = mac.macLength
        val out = ByteArray(keyLength)
        pbkdf2HmacSha256Into(
            mac = mac,
            password = password,
            salt = salt,
            iterations = iterations,
            keyLength = keyLength,
            block = ByteArray(salt.size + 4),
            u = ByteArray(hLen),
            u2 = ByteArray(hLen),
            t = ByteArray(hLen),
            out = out,
        )
        return out
    }

    /** counter 以 big-endian uint32 追加到 nonce（ALTCHA v2 默认 CounterModeUint32）。 */
    fun counterPassword(nonce: ByteArray, counter: Int): ByteArray {
        val out = ByteArray(nonce.size + 4)
        System.arraycopy(nonce, 0, out, 0, nonce.size)
        putCounterBigEndian(out, nonce.size, counter)
        return out
    }

    /** 十六进制 keyPrefix 匹配；支持奇数长度（最后一个 nibble 比较高 4 位）。 */
    fun matchesPrefix(prefixHex: String, key: ByteArray): Boolean {
        val p = prefixHex.trim().lowercase()
        if (p.isEmpty()) return false
        val bytes = decodePrefixHead(p) ?: return false
        return prefixMatches(p, bytes, key)
    }

    /** 解码前缀的整字节部分（奇数长度时丢掉最后一个 nibble，单独比较）。 */
    private fun decodePrefixHead(prefixHex: String): ByteArray? =
        hexDecode(if (prefixHex.length % 2 == 0) prefixHex else prefixHex.dropLast(1))

    /** 求解热路径使用的无分配前缀匹配：前缀字节已预解码。 */
    private fun prefixMatches(prefixHex: String, prefixBytes: ByteArray, key: ByteArray): Boolean {
        if (prefixBytes.size > key.size) return false
        for (i in prefixBytes.indices) {
            if (key[i] != prefixBytes[i]) return false
        }
        if (prefixHex.length % 2 == 0) return true
        if (prefixBytes.size >= key.size) return false
        val nibble = Character.digit(prefixHex.last(), 16)
        if (nibble < 0) return false
        return (key[prefixBytes.size].toInt() and 0xF0) == (nibble shl 4)
    }

    private fun putCounterBigEndian(target: ByteArray, offset: Int, counter: Int) {
        target[offset] = (counter ushr 24).toByte()
        target[offset + 1] = (counter ushr 16).toByte()
        target[offset + 2] = (counter ushr 8).toByte()
        target[offset + 3] = counter.toByte()
    }

    fun hexDecode(hex: String): ByteArray? {
        val s = hex.trim()
        if (s.length % 2 != 0) return null
        val out = ByteArray(s.length / 2)
        var i = 0
        while (i < s.length) {
            val hi = Character.digit(s[i], 16)
            val lo = Character.digit(s[i + 1], 16)
            if (hi < 0 || lo < 0) return null
            out[i / 2] = ((hi shl 4) or lo).toByte()
            i += 2
        }
        return out
    }

    fun hexEncode(bytes: ByteArray): String {
        val digits = "0123456789abcdef"
        val out = StringBuilder(bytes.size * 2)
        for (b in bytes) {
            val v = b.toInt() and 0xFF
            out.append(digits[v ushr 4]).append(digits[v and 0x0F])
        }
        return out.toString()
    }
}
