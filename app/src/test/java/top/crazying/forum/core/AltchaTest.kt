package top.crazying.forum.core

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64
import javax.crypto.Mac

/**
 * [Altcha] 纯 JVM 用例：PBKDF2 已知向量、counter 编码、keyPrefix 匹配、求解与 payload。
 *
 * PBKDF2 向量来自 RFC 7914 / hashcalc 常用口径，可用 Python
 * `hashlib.pbkdf2_hmac('sha256', b'password', b'salt', N, 32)` 复现；
 * 挑战向量用同口径按服务端 counter 区间（`[cost, 2*cost)` 未命中后回退 `[0, cost)`）计算。
 */
class AltchaTest {

    @Test
    fun pbkdf2HmacSha256_iterations1_matchesKnownVector() {
        val key = Altcha.pbkdf2HmacSha256(
            password = "password".toByteArray(Charsets.UTF_8),
            salt = "salt".toByteArray(Charsets.UTF_8),
            iterations = 1,
            keyLength = 32,
        )
        assertEquals(
            "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b",
            Altcha.hexEncode(key),
        )
    }

    @Test
    fun pbkdf2HmacSha256_iterations2_matchesKnownVector() {
        val key = Altcha.pbkdf2HmacSha256(
            password = "password".toByteArray(Charsets.UTF_8),
            salt = "salt".toByteArray(Charsets.UTF_8),
            iterations = 2,
            keyLength = 32,
        )
        assertEquals(
            "ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43",
            Altcha.hexEncode(key),
        )
    }

    @Test
    fun pbkdf2HmacSha256_iterations4096_matchesKnownVector() {
        val key = Altcha.pbkdf2HmacSha256(
            password = "password".toByteArray(Charsets.UTF_8),
            salt = "salt".toByteArray(Charsets.UTF_8),
            iterations = 4096,
            keyLength = 32,
        )
        assertEquals(
            "c5e478d59288c841aa530db6845c4c8d962893a001ce4e11a4963873aa98134a",
            Altcha.hexEncode(key),
        )
    }

    @Test
    fun counterPassword_appendsBigEndianUint32() {
        val nonce = ByteArray(16) { it.toByte() }
        val expected = ByteArray(20)
        for (i in 0 until 16) expected[i] = i.toByte()
        expected[16] = 0x01.toByte()
        expected[17] = 0x02.toByte()
        expected[18] = 0x03.toByte()
        expected[19] = 0x04.toByte()

        assertArrayEquals(expected, Altcha.counterPassword(nonce, 0x01020304))
        assertEquals(
            "000102030405060708090a0b0c0d0e0f01020304",
            Altcha.hexEncode(Altcha.counterPassword(nonce, 0x01020304)),
        )
    }

    @Test
    fun matchesPrefix_evenLength() {
        assertTrue(Altcha.matchesPrefix("120fb6cf", knownKey()))
    }

    @Test
    fun matchesPrefix_oddLengthComparesHighNibble() {
        assertTrue(Altcha.matchesPrefix("120fb6c", knownKey()))
        assertFalse(Altcha.matchesPrefix("120fb6d", knownKey()))
    }

    @Test
    fun matchesPrefix_isCaseInsensitive() {
        assertTrue(Altcha.matchesPrefix(" 120FB6CF ", knownKey()))
    }

    @Test
    fun matchesPrefix_rejectsMismatchAndInvalidPrefix() {
        assertFalse(Altcha.matchesPrefix("120fb6ce", knownKey()))
        assertFalse(Altcha.matchesPrefix("", knownKey()))

        val shortKey = Altcha.hexDecode("120fb6cf")!!
        assertTrue(Altcha.matchesPrefix("120fb6cf", shortKey))
        assertTrue(Altcha.matchesPrefix("120fb6c", shortKey))
        // 前缀字节数超过 key 长度
        assertFalse(Altcha.matchesPrefix("120fb6cf00", shortKey))
        // 奇数长度前缀已占满 key，无法再比较高 4 位
        assertFalse(Altcha.matchesPrefix("120fb6c", Altcha.hexDecode("120fb6")!!))
    }

    @Test
    fun parse_rejectsMalformedChallenge() {
        assertNull(Altcha.parse(null))
        assertNull(Altcha.parse(JSONObject()))
        assertNull(
            Altcha.parse(
                JSONObject().put(
                    "parameters",
                    JSONObject().put("algorithm", "PBKDF2/SHA-256"),
                ),
            ),
        )
        // 缺少 keyPrefix 同样不合法
        assertNull(Altcha.parse(challengeJson(keyPrefix = "")))
    }

    @Test
    fun parse_readsParametersAndLowercasesHex() {
        val parsed = Altcha.parse(
            challengeJson(
                algorithm = "pbkdf2/sha-256",
                nonce = NONCE_HEX.uppercase(),
                salt = SALT_HEX.uppercase(),
                keyPrefix = DERIVED_HEX.uppercase(),
            ),
        )
        assertNotNull(parsed)
        assertEquals("PBKDF2/SHA-256", parsed!!.algorithm.uppercase())
        assertEquals(NONCE_HEX, parsed.nonceHex)
        assertEquals(SALT_HEX, parsed.saltHex)
        assertEquals(COST, parsed.cost)
        assertEquals(32, parsed.keyLength)
        assertEquals(DERIVED_HEX, parsed.keyPrefixHex)
        assertEquals(0L, parsed.expiresAt)
    }

    @Test
    fun solve_findsServerCounterAndPayloadCarriesChallengeAndSolution() {
        val challenge = Altcha.parse(challengeJson())
        assertNotNull(challenge)
        challenge!!

        val outcome = runBlocking { Altcha.solve(challenge, workers = 1) }
        assertTrue("未命中：$outcome", outcome is SolveOutcome.Solved)
        val solution = (outcome as SolveOutcome.Solved).solution
        assertEquals(137, solution.counter)
        assertEquals(DERIVED_HEX, solution.derivedKeyHex)

        val payload = Altcha.payload(challenge, solution)
        val decoded = JSONObject(String(Base64.getDecoder().decode(payload), Charsets.UTF_8))
        assertTrue(decoded.has("challenge"))
        assertTrue(decoded.has("solution"))
        assertEquals(137, decoded.getJSONObject("solution").getInt("counter"))
        assertEquals(DERIVED_HEX, decoded.getJSONObject("solution").getString("derivedKey"))
        val params = decoded.getJSONObject("challenge").getJSONObject("parameters")
        assertEquals("PBKDF2/SHA-256", params.getString("algorithm"))
        assertEquals(NONCE_HEX, params.getString("nonce"))
    }

    @Test
    fun pbkdf2HmacSha256Into_reusesBuffersWithNonAsciiPassword() {
        val mac = Mac.getInstance("HmacSHA256")
        val password = "pässwörd€".toByteArray(Charsets.UTF_8)
        val salt = "salt".toByteArray(Charsets.UTF_8)
        val block = ByteArray(salt.size + 4)
        val u = ByteArray(32)
        val u2 = ByteArray(32)
        val t = ByteArray(32)
        val out = ByteArray(32)

        Altcha.pbkdf2HmacSha256Into(mac, password, salt, 2, 32, block, u, u2, t, out)
        assertEquals(
            "0ae698df272989143f94a6b82baa21159142ce90358e74df93baca3e6167dbae",
            Altcha.hexEncode(out),
        )

        // 同一组缓冲区再算一次（验证 Mac / 缓冲状态已复位）
        out.fill(0)
        Altcha.pbkdf2HmacSha256Into(mac, password, salt, 2, 32, block, u, u2, t, out)
        assertEquals(
            "0ae698df272989143f94a6b82baa21159142ce90358e74df93baca3e6167dbae",
            Altcha.hexEncode(out),
        )

        // 多 block（keyLength=64）与兼容包装一致
        val out64 = ByteArray(64)
        Altcha.pbkdf2HmacSha256Into(
            mac, "password".toByteArray(), "salt".toByteArray(), 2, 64, block, u, u2, t, out64,
        )
        assertEquals(
            "ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43" +
                "830651afcb5c862f0b249bd031f7a67520d136470f5ec271ece91c07773253d9",
            Altcha.hexEncode(out64),
        )
        assertArrayEquals(
            Altcha.pbkdf2HmacSha256(
                "password".toByteArray(),
                "salt".toByteArray(),
                2,
                64,
            ),
            out64,
        )
    }

    @Test
    fun parse_rejectsOutOfRangeParameters() {
        assertNull(Altcha.parse(challengeJson(cost = 0)))
        assertNull(Altcha.parse(challengeJson(cost = 20_001)))
        assertNull(Altcha.parse(challengeJson(keyLength = 0)))
        assertNull(Altcha.parse(challengeJson(keyLength = 65)))
        // keyPrefix 长度不得超过 keyLength * 2
        assertNull(Altcha.parse(challengeJson(keyLength = 4, keyPrefix = "123456789")))
        // nonce / salt hex 长度上限 128
        assertNull(Altcha.parse(challengeJson(nonce = "a".repeat(130))))
        assertNull(Altcha.parse(challengeJson(salt = "a".repeat(130))))
        // 边界值可接受
        assertNotNull(Altcha.parse(challengeJson(cost = 20_000, keyLength = 64)))
        assertNotNull(Altcha.parse(challengeJson(nonce = "a".repeat(128), salt = "b".repeat(128))))
    }

    @Test
    fun solve_multipleWorkersAgree() {
        val challenge = Altcha.parse(
            challengeJson(
                cost = CHEAP_COST,
                nonce = CHEAP_NONCE_HEX,
                salt = CHEAP_SALT_HEX,
                keyPrefix = CHEAP_DERIVED_HEX,
            ),
        )
        assertNotNull(challenge)
        challenge!!

        val single = runBlocking { Altcha.solve(challenge, workers = 1) }
        val multi = runBlocking { Altcha.solve(challenge, workers = 4) }
        assertTrue("single=$single", single is SolveOutcome.Solved)
        assertTrue("multi=$multi", multi is SolveOutcome.Solved)
        assertEquals(CHEAP_COUNTER, (single as SolveOutcome.Solved).solution.counter)
        assertEquals(CHEAP_COUNTER, (multi as SolveOutcome.Solved).solution.counter)
        assertEquals(single.solution.derivedKeyHex, multi.solution.derivedKeyHex)
        assertEquals(CHEAP_DERIVED_HEX, single.solution.derivedKeyHex)
    }

    @Test
    fun solve_timesOutAtDeadline() {
        val challenge = AltchaChallenge(
            raw = JSONObject(),
            algorithm = "PBKDF2/SHA-256",
            nonceHex = NONCE_HEX,
            saltHex = SALT_HEX,
            cost = 20_000,
            keyLength = 32,
            keyPrefixHex = "f".repeat(64),
            expiresAt = 0L,
        )
        val outcome = runBlocking { Altcha.solve(challenge, workers = 1, deadlineMs = 1L) }
        assertSame(SolveOutcome.TimedOut, outcome)
    }

    @Test
    fun solve_withoutDeadlineStillSolves() {
        val challenge = Altcha.parse(
            challengeJson(
                cost = CHEAP_COST,
                nonce = CHEAP_NONCE_HEX,
                salt = CHEAP_SALT_HEX,
                keyPrefix = CHEAP_DERIVED_HEX,
            ),
        )
        assertNotNull(challenge)
        val outcome = runBlocking { Altcha.solve(challenge!!, workers = 1, deadlineMs = 0L) }
        assertTrue("deadline=0 应表示不限制：$outcome", outcome is SolveOutcome.Solved)
        assertEquals(CHEAP_COUNTER, (outcome as SolveOutcome.Solved).solution.counter)
    }

    @Test
    fun solve_cancelledByFlag() {
        val challenge = Altcha.parse(challengeJson())
        assertNotNull(challenge)
        val outcome = runBlocking {
            Altcha.solve(challenge!!, workers = 2, isCancelled = { true })
        }
        assertSame(SolveOutcome.Cancelled, outcome)
    }

    @Test
    fun solve_noMatchWhenPrefixNeverMatches() {
        val challenge = Altcha.parse(
            challengeJson(cost = 10, keyPrefix = "f".repeat(64)),
        )
        assertNotNull(challenge)
        val outcome = runBlocking { Altcha.solve(challenge!!, workers = 2) }
        assertSame(SolveOutcome.NoMatch, outcome)
    }

    @Test
    fun solve_rejectsUnsupportedAlgorithm() {
        val challenge = Altcha.parse(challengeJson(algorithm = "PBKDF2/SHA-1"))
        assertNotNull(challenge)
        val outcome = runBlocking { Altcha.solve(challenge!!, workers = 1) }
        assertSame(SolveOutcome.NoMatch, outcome)
    }

    @Test
    fun defaultWorkers_isWithinOneToFour() {
        val workers = Altcha.defaultWorkers()
        assertTrue("workers=$workers", workers in 1..4)
    }

    @Test
    fun isExpired_comparesExpiresAtInSeconds() {
        val challenge = buildChallenge(expiresAt = 1_800_000_000L)
        assertFalse(Altcha.isExpired(challenge, nowMs = 1_799_999_999_999L))
        assertTrue(Altcha.isExpired(challenge, nowMs = 1_800_000_000_000L))
        assertTrue(Altcha.isExpired(challenge, nowMs = 1_800_000_000_001L))
        // 0 表示无期限
        assertFalse(Altcha.isExpired(buildChallenge(expiresAt = 0L), nowMs = Long.MAX_VALUE))
    }

    // ────────────────── APP 专用零 PoW 通道 ──────────────────

    @Test
    fun appProof_matchesServerVector() {
        // 向量由 Python hmac.new(secret, b"app-captcha:v1:<challenge>:<ts>", sha256).hexdigest() 生成，
        // 与服务端 internal/altcha/appProofSignature 同口径（UTF-8 明文 + 小写 hex）。
        assertEquals(
            "360663eaffba0e3d783d0c63473a9d682ac959605c4d8ea64955870aff9b21eb",
            Altcha.appProof("test-app-secret", "0123456789abcdef0123456789abcdef", 1_700_000_000L),
        )
        assertEquals(
            "06fea3e8189db2186318e1b390029a0eebd7d3ee8fac7c7509a36a726903b539",
            Altcha.appProof("another-secret", "ffffffffffffffffffffffffffffffff", 1_700_000_123L),
        )
    }

    @Test
    fun appProof_rejectsBlankInput() {
        assertThrows(IllegalArgumentException::class.java) { Altcha.appProof("", "abc", 1L) }
        assertThrows(IllegalArgumentException::class.java) { Altcha.appProof("s", "", 1L) }
        assertThrows(IllegalArgumentException::class.java) { Altcha.appProof("s", "abc", 0L) }
    }

    private fun knownKey(): ByteArray = Altcha.hexDecode(
        "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b",
    )!!

    private fun buildChallenge(expiresAt: Long): AltchaChallenge = AltchaChallenge(
        raw = JSONObject(),
        algorithm = "PBKDF2/SHA-256",
        nonceHex = NONCE_HEX,
        saltHex = SALT_HEX,
        cost = COST,
        keyLength = 32,
        keyPrefixHex = DERIVED_HEX.take(8),
        expiresAt = expiresAt,
    )

    private fun challengeJson(
        algorithm: String = "PBKDF2/SHA-256",
        nonce: String = NONCE_HEX,
        salt: String = SALT_HEX,
        cost: Int = COST,
        keyLength: Int = 32,
        keyPrefix: String = DERIVED_HEX,
    ): JSONObject = JSONObject().put(
        "parameters",
        JSONObject()
            .put("algorithm", algorithm)
            .put("nonce", nonce)
            .put("salt", salt)
            .put("cost", cost)
            .put("keyLength", keyLength)
            .put("keyPrefix", keyPrefix)
            .put("expiresAt", 0),
    )

    private companion object {
        const val NONCE_HEX = "000102030405060708090a0b0c0d0e0f"
        const val SALT_HEX = "101112131415161718191a1b1c1d1e1f"
        const val COST = 1000

        /** nonce+counter(0x137) 经 PBKDF2-HMAC-SHA256(salt, 1000, 32) 的固定输出。 */
        const val DERIVED_HEX = "d2e1ffb1f4071e13cff6691e9b777f8f51139ef5dcc8af89c672e19a87bb2aa0"

        // 小 cost 挑战：counter 3 在回退区间 [0, cost)，用于验证 1/4 worker 结果一致。
        const val CHEAP_NONCE_HEX = "aabbccddeeff00112233445566778899"
        const val CHEAP_SALT_HEX = "00112233445566778899aabbccddeeff"
        const val CHEAP_COST = 5
        const val CHEAP_COUNTER = 3
        const val CHEAP_DERIVED_HEX =
            "a40d912298fe94883043a9d5e6ab2ccb1e53fa93f256ffd1aafb321e398e97aa"
    }
}
