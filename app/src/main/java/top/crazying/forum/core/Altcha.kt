package top.crazying.forum.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import okio.ByteString.Companion.encodeUtf8
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicLong
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

object Altcha {

    private const val DEFAULT_COST = 5000
    private const val DEFAULT_KEY_LENGTH = 32
    private const val MAX_PREFIX_HEX = 128

    /** 解析服务端返回的 Challenge JSON；结构不合法返回 null。 */
    fun parse(json: JSONObject?): AltchaChallenge? {
        val params = json?.optJSONObject("parameters") ?: return null
        val algorithm = params.optString("algorithm", "").trim()
        val nonce = params.optString("nonce", "").trim()
        val salt = params.optString("salt", "").trim()
        if (algorithm.isEmpty() || nonce.isEmpty() || salt.isEmpty()) return null
        val cost = params.optInt("cost", DEFAULT_COST).takeIf { it > 0 } ?: DEFAULT_COST
        val keyLength = params.optInt("keyLength", DEFAULT_KEY_LENGTH).takeIf { it > 0 }
            ?: DEFAULT_KEY_LENGTH
        val prefix = params.optString("keyPrefix", "").trim().lowercase()
        if (prefix.isEmpty() || prefix.length > MAX_PREFIX_HEX) return null
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

    /**
     * 求解。多协程分片；`onProgress` 会从后台线程回调（调用方自行切主线程）。
     *
     * @param workers 分片数，默认 CPU 核数（1~8）。
     */
    suspend fun solve(
        challenge: AltchaChallenge,
        workers: Int = Runtime.getRuntime().availableProcessors().coerceIn(1, 8),
        onProgress: (attempts: Long, elapsedMs: Long) -> Unit = { _, _ -> },
        isCancelled: () -> Boolean = { false },
    ): AltchaSolution? {
        val algorithm = challenge.algorithm.uppercase()
        if (!algorithm.startsWith("PBKDF2/SHA-256")) {
            // 服务端可配置算法；当前生产固定 PBKDF2/SHA-256。
            return null
        }
        val nonce = hexDecode(challenge.nonceHex) ?: return null
        val salt = hexDecode(challenge.saltHex) ?: return null
        val prefix = challenge.keyPrefixHex
        val started = System.currentTimeMillis()
        val attempts = AtomicLong(0)
        val found = AtomicReference<AltchaSolution?>(null)
        val nWorkers = workers.coerceIn(1, 8)

        suspend fun scan(from: Int, until: Int) {
            if (from >= until) return
            coroutineScope {
                (0 until nWorkers).map { index ->
                    async(Dispatchers.Default) {
                        var n = from + index
                        var local = 0L
                        while (n < until) {
                            if (found.get() != null || isCancelled()) return@async
                            val derived = pbkdf2HmacSha256(
                                password = counterPassword(nonce, n),
                                salt = salt,
                                iterations = challenge.cost,
                                keyLength = challenge.keyLength,
                            )
                            if (matchesPrefix(prefix, derived)) {
                                val elapsed = System.currentTimeMillis() - started
                                found.compareAndSet(
                                    null,
                                    AltchaSolution(maxOf(0, n), hexEncode(derived), elapsed),
                                )
                                return@async
                            }
                            n += nWorkers
                            local++
                            if (local and 0x3F == 0L) {
                                val total = attempts.addAndGet(64L)
                                onProgress(total, System.currentTimeMillis() - started)
                            }
                        }
                        val rest = local and 0x3F
                        if (rest != 0L) {
                            val total = attempts.addAndGet(rest)
                            onProgress(total, System.currentTimeMillis() - started)
                        }
                    }
                }.awaitAll()
            }
        }

        // 1) 服务端生成区间；2) 回退全量低区间。
        val cost = challenge.cost.coerceAtLeast(1)
        scan(cost, min(cost * 2, Int.MAX_VALUE - 1))
        if (found.get() != null || isCancelled()) return found.get()
        scan(0, cost)
        return found.get()
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

    /** PBKDF2-HMAC-SHA256（单块/多块通用）。 */
    fun pbkdf2HmacSha256(
        password: ByteArray,
        salt: ByteArray,
        iterations: Int,
        keyLength: Int,
    ): ByteArray {
        require(iterations > 0) { "iterations must be > 0" }
        require(keyLength > 0) { "keyLength must be > 0" }
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(password, "HmacSHA256"))
        val block = ByteArray(salt.size + 4)
        System.arraycopy(salt, 0, block, 0, salt.size)
        val out = ByteArray(keyLength)
        var offset = 0
        var blockIndex = 1
        while (offset < keyLength) {
            block[salt.size] = (blockIndex ushr 24).toByte()
            block[salt.size + 1] = (blockIndex ushr 16).toByte()
            block[salt.size + 2] = (blockIndex ushr 8).toByte()
            block[salt.size + 3] = blockIndex.toByte()
            var u = mac.doFinal(block)
            val t = u.copyOf()
            var i = 1
            while (i < iterations) {
                u = mac.doFinal(u)
                for (j in t.indices) t[j] = (t[j].toInt() xor u[j].toInt()).toByte()
                i++
            }
            val take = min(t.size, keyLength - offset)
            System.arraycopy(t, 0, out, offset, take)
            offset += take
            blockIndex++
        }
        return out
    }

    /** counter 以 big-endian uint32 追加到 nonce（ALTCHA v2 默认 CounterModeUint32）。 */
    fun counterPassword(nonce: ByteArray, counter: Int): ByteArray {
        val out = ByteArray(nonce.size + 4)
        System.arraycopy(nonce, 0, out, 0, nonce.size)
        out[nonce.size] = (counter ushr 24).toByte()
        out[nonce.size + 1] = (counter ushr 16).toByte()
        out[nonce.size + 2] = (counter ushr 8).toByte()
        out[nonce.size + 3] = counter.toByte()
        return out
    }

    /** 十六进制 keyPrefix 匹配；支持奇数长度（最后一个 nibble 比较高 4 位）。 */
    fun matchesPrefix(prefixHex: String, key: ByteArray): Boolean {
        val p = prefixHex.trim().lowercase()
        if (p.isEmpty()) return false
        val evenLen = p.length and 1.inv()
        val head = p.substring(0, evenLen)
        val bytes = hexDecode(head) ?: return false
        if (bytes.size > key.size) return false
        for (i in bytes.indices) {
            if (key[i] != bytes[i]) return false
        }
        if (p.length % 2 == 0) return true
        if (bytes.size >= key.size) return false
        val nibble = Character.digit(p.last(), 16)
        if (nibble < 0) return false
        return (key[bytes.size].toInt() and 0xF0) == (nibble shl 4)
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
