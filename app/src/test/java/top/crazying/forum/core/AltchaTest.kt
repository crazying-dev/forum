package top.crazying.forum.core

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

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

        val solution = runBlocking { Altcha.solve(challenge, workers = 1) }
        assertNotNull(solution)
        solution!!
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
    fun isExpired_comparesExpiresAtInSeconds() {
        val challenge = buildChallenge(expiresAt = 1_800_000_000L)
        assertFalse(Altcha.isExpired(challenge, nowMs = 1_799_999_999_999L))
        assertTrue(Altcha.isExpired(challenge, nowMs = 1_800_000_000_000L))
        assertTrue(Altcha.isExpired(challenge, nowMs = 1_800_000_000_001L))
        // 0 表示无期限
        assertFalse(Altcha.isExpired(buildChallenge(expiresAt = 0L), nowMs = Long.MAX_VALUE))
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
        keyPrefix: String = DERIVED_HEX,
    ): JSONObject = JSONObject().put(
        "parameters",
        JSONObject()
            .put("algorithm", algorithm)
            .put("nonce", nonce)
            .put("salt", salt)
            .put("cost", COST)
            .put("keyLength", 32)
            .put("keyPrefix", keyPrefix)
            .put("expiresAt", 0),
    )

    private companion object {
        const val NONCE_HEX = "000102030405060708090a0b0c0d0e0f"
        const val SALT_HEX = "101112131415161718191a1b1c1d1e1f"
        const val COST = 1000

        /** nonce+counter(0x137) 经 PBKDF2-HMAC-SHA256(salt, 1000, 32) 的固定输出。 */
        const val DERIVED_HEX = "d2e1ffb1f4071e13cff6691e9b777f8f51139ef5dcc8af89c672e19a87bb2aa0"
    }
}
