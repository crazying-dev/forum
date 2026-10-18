package top.crazying.forum.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.core.NewEraDate
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.components.ForumCard
import top.crazying.forum.ui.components.ForumTextField
import top.crazying.forum.ui.components.GhostButton
import top.crazying.forum.ui.components.InfoRow
import top.crazying.forum.ui.components.Muted
import top.crazying.forum.ui.components.PageScaffold
import top.crazying.forum.ui.components.SectionTitle
import kotlin.math.abs

/** 换算结果（[text] 为空表示还没输入）。 */
private data class ConvResult(val text: String = "", val error: Boolean = false)

/**
 * 「年制换算」页：无限年 ⇄ 公元年 双向换算。
 *
 * 入口：「我的 → 快捷入口 → 年制换算」。
 * 口径与 Web「无限年换算」弹窗、Windows 设置页「无限年换算」完全一致：
 * 无限元年 = 公元 1604 年（1 起算），公元 1603 年 = 「无限前 1 年」，不存在无限 0 年。
 */
@Composable
fun YearConvertScreen(nav: Navigator) {
    var wyText by remember { mutableStateOf("") }
    var ceText by remember { mutableStateOf("") }
    val yearMode by App.yearMode

    val fromWuxian = remember(wyText) { convertWuxianToGregorian(wyText) }
    val fromCe = remember(ceText) { convertGregorianToWuxian(ceText) }

    PageScaffold(title = "年制换算", onBack = { nav.pop() }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ForumCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionTitle("年制基准")
                    Muted(
                        "无限元年 = 公元 1604 年，从 1 起算；公元 1603 年为「无限前 1 年」。" +
                            "无限历与公元纪年都不存在 0 年。公元前的年份请在公元输入框里填负数（如 -1 = 公元前 1 年）。",
                        maxLines = 4,
                    )
                    InfoRow(
                        "当前全站年制",
                        if (yearMode == Constants.YEAR_MODE_CE) "公元年" else "无限年",
                    )
                }
            }

            ForumCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionTitle("无限年 → 公元年")
                    ForumTextField(
                        value = wyText,
                        onValueChange = { wyText = it },
                        placeholder = "无限年，如 400；无限前请填负数，如 -1",
                    )
                    ResultLine(fromWuxian, "填上方数字即可实时换算")
                }
            }

            ForumCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionTitle("公元年 → 无限年")
                    ForumTextField(
                        value = ceText,
                        onValueChange = { ceText = it },
                        placeholder = "公元年，如 2010；公元前请填负数，如 -1",
                    )
                    ResultLine(fromCe, "填上方数字即可实时换算")
                }
            }

            GhostButton(
                text = "清空",
                onClick = { wyText = ""; ceText = "" },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/** 结果行：未输入时显示提示语，出错时用危险色。 */
@Composable
private fun ResultLine(result: ConvResult, hint: String) {
    val colors = ForumTheme.colors
    val blank = result.text.isBlank()
    Text(
        text = if (blank) hint else result.text,
        color = when {
            blank -> colors.textMuted
            result.error -> colors.danger
            else -> colors.textSecondary
        },
        fontSize = 13.sp,
    )
}

/** 无限年（可为负，表示无限前）→ 公元年。 */
private fun convertWuxianToGregorian(raw: String): ConvResult {
    val s = raw.trim()
    if (s.isEmpty()) return ConvResult()
    val n = s.toIntOrNull() ?: return ConvResult("请输入整数", error = true)
    if (n == 0) return ConvResult("无限历没有 0 年（元年即公元 1604 年）", error = true)
    val era = NewEraDate(abs(n), isBefore = n < 0)
    val ce = TimeFmt.newEraToGregorian(era.yearNum, era.isBefore)
    return ConvResult("${era.label} = ${TimeFmt.ceText(ce)}")
}

/** 公元年 → 无限年；公元 0 年不存在，负数 = 公元前 |n| 年（与 Web 端口径一致）。 */
private fun convertGregorianToWuxian(raw: String): ConvResult {
    val s = raw.trim()
    if (s.isEmpty()) return ConvResult()
    val n = s.toIntOrNull() ?: return ConvResult("请输入整数", error = true)
    // 公元纪年无 0 年：不得输出「公元 0 年 = 无限前 1604 年」
    // 负数 = 公元前 |n| 年（与「无限年」输入负数表示「无限前」同口径）；
    // 公元前 M 年按天文纪年记作 (1 − M)，故先归一再加换算，避免差一年。
    val astro = TimeFmt.ceInputToAstronomical(n)
        ?: return ConvResult("公元纪年没有 0 年（公元前 1 年之后即公元 1 年）", error = true)
    val era = TimeFmt.gregorianToNewEra(astro)
    return ConvResult("${TimeFmt.ceText(astro)} = ${era.label}")
}
