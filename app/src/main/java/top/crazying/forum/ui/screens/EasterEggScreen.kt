package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.Api
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.EmptyBox
import top.crazying.forum.ui.components.HDivider
import top.crazying.forum.ui.components.HtmlBody
import top.crazying.forum.ui.components.LoadingBox
import top.crazying.forum.ui.components.Muted
import top.crazying.forum.ui.components.PrimaryButton
import top.crazying.forum.ui.components.SectionTitle
import kotlin.coroutines.cancellation.CancellationException

/** 一条彩蛋 / 每日一言。 */
private data class EggPiece(
    val title: String,
    val text: String,
    /** 彩蛋的 `Text` 里带 `<br>`，需要按 HTML 渲染；每日一言是纯文本。 */
    val html: Boolean,
)

/**
 * 彩蛋页（底部第 6 个标签）。
 *
 * 与网页端手机版底栏的「彩蛋」入口对齐：点一下随机给一条内容——
 * 50% 概率是**每日一言**（第三方接口，与 `AfterBody.js` 用的是同一个），
 * 50% 概率是本站的 `/Easter-Egg`；任一来源拿不到会自动改拿另一个。
 */
@Composable
fun EasterEggScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val scope = rememberCoroutineScope()

    var busy by remember { mutableStateOf(false) }
    var piece by remember { mutableStateOf<EggPiece?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var drawn by remember { mutableStateOf(false) }

    fun draw() {
        if (busy) return
        busy = true
        error = null
        scope.launch {
            val got = drawOne(App.api)
            busy = false
            if (got == null) error = "这次什么也没抽到，稍后再试试吧。" else piece = got
        }
    }

    // 首次进入自动抽一条（与 Windows 端 `play=True` 同义）
    LaunchedEffect(Unit) {
        if (!drawn) {
            drawn = true
            draw()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("彩蛋", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold)

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            SectionTitle("今日彩蛋")

            when {
                busy && piece == null -> LoadingBox(text = "正在抽取…")
                else -> {
                    val got = piece
                    if (got != null) {
                        if (got.title.isNotBlank()) {
                            Text(
                                text = got.title,
                                color = colors.textPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                        if (got.text.isNotBlank()) {
                            if (got.html) {
                                HtmlBody(html = got.text, fontSizeSp = 15f)
                            } else {
                                Text(
                                    text = got.text,
                                    color = colors.textSecondary,
                                    fontSize = 15.sp,
                                )
                            }
                        }
                    }
                }
            }

            error?.let { message ->
                Text(text = message, color = colors.danger, fontSize = 13.sp)
            }

            if (piece == null && !busy && error == null) {
                Text(text = "点下面的按钮抽一条彩蛋。", color = colors.textMuted, fontSize = 13.sp)
            }

            PrimaryButton(
                text = if (busy) "正在抽取…" else "🎁 再来一个彩蛋",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    if (piece == null && error != null) error = null
                    draw()
                },
            )

            HDivider()
            Muted("每次点击会随机奉上一条彩蛋或每日一言。", maxLines = 2)
        }

        // 顺路看看（与 Windows 端彩蛋页的「顺路看看」一致）
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(4.dp),
        ) {
            EggLink("访问 WIKI") { nav.switchTab(Screen.Wiki) }
            EggLink("进入世界频道") { nav.switchTab(Screen.World) }
            EggLink("搜索帖子与用户") { nav.push(Screen.Search()) }
        }

        EmptyBox("妖精论坛 · 彩蛋")
    }
}

@Composable
private fun EggLink(text: String, onClick: () -> Unit) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable { onClick() }
            .padding(horizontal = 12.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, color = colors.textPrimary, fontSize = 14.sp, modifier = Modifier.weight(1f))
        Text("›", color = colors.textMuted, fontSize = 16.sp)
    }
}

// ────────────────── 抽取逻辑 ──────────────────

/** 抽一条：50% 每日一言 / 50% 彩蛋，任一失败自动改拿另一个；都失败返回 null。 */
private suspend fun drawOne(api: Api): EggPiece? {
    return if (Math.random() < 0.5) {
        fetchSentence(api) ?: fetchEgg(api)
    } else {
        fetchEgg(api) ?: fetchSentence(api)
    }
}

private suspend fun fetchSentence(api: Api): EggPiece? {
    val plain = try {
        api.fetchText(Constants.SENTENCE_TEXT_URL)?.trim()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }
    if (!plain.isNullOrEmpty()) return EggPiece("每日一言", plain, false)

    val result = try {
        api.fetchExternalJson(Constants.SENTENCE_JSON_URL)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        return null
    }
    val obj = result.obj() ?: return null
    val content = obj.optString("content", "").trim()
    if (content.isEmpty()) return null
    val extra = ArrayList<String>(2)
    val author = obj.optString("author", "").trim()
    val source = obj.optString("source", "").trim()
    if (author.isNotEmpty()) extra.add(author)
    if (source.isNotEmpty()) extra.add("《$source》")
    val line = if (extra.isEmpty()) content else content + " —— " + extra.joinToString(" ")
    return EggPiece("每日一言", line, false)
}

private suspend fun fetchEgg(api: Api): EggPiece? {
    val result = try {
        api.easterEgg()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        return null
    }
    if (!result.ok) return null
    val obj = result.obj() ?: return null
    val name = obj.optString("Name", "").trim()
    val text = obj.optString("Text", "").trim()
    if (name.isEmpty() && text.isEmpty()) return null
    return EggPiece(name.ifEmpty { "彩蛋" }, text, true)
}
