package top.crazying.forum.core

import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 可选的本地端到端：只设置了 `ALTCHA_LIVE_URL` 时运行。
 *
 * 启动本地 ouo（ALTCHA_ENABLED=true、低 cost）后：
 * `ALTCHA_LIVE_URL=http://127.0.0.1:18090 ./gradlew testDebugUnitTest`
 * 即可验证「challenge → Kotlin 求解 → verify → grant」全链路。
 */
class AltchaLiveTest {

    @Test
    fun solveAndVerifyAgainstLocalServer() {
        val base = System.getenv("ALTCHA_LIVE_URL")?.trim()?.trimEnd('/').orEmpty()
        if (base.isEmpty()) return

        val client = OkHttpClient()
        val challengeText = client.newCall(
            Request.Builder()
                .url("$base/ov2/api/captcha/challenge")
                .header("Origin", base)
                .build(),
        ).execute().use { response ->
            assertTrue("challenge HTTP ${response.code}", response.isSuccessful)
            response.body?.string().orEmpty()
        }
        val challenge = Altcha.parse(JSONObject(challengeText))
            ?: throw AssertionError("challenge 解析失败：$challengeText")
        val solution = runBlocking { Altcha.solve(challenge, workers = 2) }
            ?: throw AssertionError("求解失败")

        val payload = Altcha.payload(challenge, solution)
        val body = JSONObject().put("altcha", payload).toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType())
        val verifyText = client.newCall(
            Request.Builder()
                .url("$base/ov2/api/captcha/verify")
                .header("Origin", base)
                .post(body)
                .build(),
        ).execute().use { response ->
            assertTrue("verify HTTP ${response.code}", response.isSuccessful)
            response.body?.string().orEmpty()
        }
        val verify = JSONObject(verifyText)
        assertTrue("verify 未成功：$verifyText", verify.optBoolean("success", false))
        assertTrue("grant 为空：$verifyText", verify.optString("grant", "").isNotBlank())
    }
}
