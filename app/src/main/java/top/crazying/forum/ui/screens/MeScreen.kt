package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.CheckResult
import top.crazying.forum.core.Constants
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.core.Updater
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.theme.ThemeResolver
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*

/**
 * 「我的」页：资料卡 + 入口 + 设置（外观 / 年制 / 关于）。
 *
 * 设置里只列出 day / night / auto 三个**基础主题**；
 * 国庆浅/深是假期内的强制叠加层，不在此处出现。
 */
@Composable
fun MeScreen(nav: Navigator) {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val me = App.user.value
    val themePref by App.themePref
    val yearMode by App.yearMode
    val holiday = ThemeResolver.isNationalDay()

    var busy by remember { mutableStateOf(false) }
    var checking by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("我的", color = colors.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold)

        // ── 资料卡 ──
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (me == null) {
                Text("还没有登录", color = colors.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                Text("登录后即可发帖、评论、收藏与关注他人", color = colors.textMuted, fontSize = 12.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    PrimaryButton(text = "登录", onClick = { nav.push(Screen.Auth(false)) })
                    GhostButton(text = "注册", onClick = { nav.push(Screen.Auth(true)) })
                }
            } else {
                val name = me.optString("name", "")
                val avatar = me.optString("avatar", "")
                val email = me.optString("email", "")
                val intro = me.optString("intro", "")
                val uid = me.optString("id", "")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Avatar(avatar, 56.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(name, color = colors.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        Text(email, color = colors.textMuted, fontSize = 12.sp)
                    }
                    GhostButton(text = "主页", onClick = { if (uid.isNotBlank()) nav.push(Screen.UserProfile(uid)) })
                }
                if (intro.isNotBlank()) {
                    Text(intro, color = colors.textSecondary, fontSize = 13.sp)
                }
                HDivider()
                GhostButton(
                    text = if (busy) "正在退出…" else "退出登录",
                    enabled = !busy,
                    tint = colors.danger,
                    onClick = {
                        if (busy) return@GhostButton
                        busy = true
                        scope.launch {
                            runCatching { App.api.logout() }
                            busy = false
                            toast(context, "已退出登录")
                        }
                    },
                )
            }
        }

        // ── 外观 ──
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionTitle("外观")
            Muted(if (holiday) "国庆节假期内已自动叠加国庆主题（不可手动选择）" else "浅色 / 深色 / 跟随系统")
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Pill("浅色", active = themePref == Constants.THEME_DAY) {
                    App.setThemePref(Constants.THEME_DAY)
                }
                Pill("深色", active = themePref == Constants.THEME_NIGHT) {
                    App.setThemePref(Constants.THEME_NIGHT)
                }
                Pill("跟随系统", active = themePref == Constants.THEME_AUTO) {
                    App.setThemePref(Constants.THEME_AUTO)
                }
            }
            if (holiday) {
                Text(
                    text = "※ 国庆假期内：浅色 → 国庆浅色，深色 → 国庆深色，跟随系统 → 国庆浅色",
                    color = colors.primary,
                    fontSize = 12.sp,
                )
            }
        }

        // ── 年制 ──
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionTitle("年制")
            Muted("影响帖子与评论里时间的年份显示")
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Pill("无限年", active = yearMode == Constants.YEAR_MODE_WUXIAN) {
                    App.setYearMode(Constants.YEAR_MODE_WUXIAN)
                }
                Pill("公元年", active = yearMode == Constants.YEAR_MODE_CE) {
                    App.setYearMode(Constants.YEAR_MODE_CE)
                }
            }
            ExampleYearRow()
        }

        // ── 关于 ──
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            SectionTitle("关于")
            InfoRow("版本", Constants.APP_VERSION)
            InfoRow("服务端", Constants.BASE_URL)
            InfoRow("客户端标识", Constants.CLIENT_UA)
            HDivider()
            PrimaryButton(
                text = if (checking) "正在检查…" else "检查更新",
                enabled = !checking,
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    if (checking) return@PrimaryButton
                    checking = true
                    scope.launch {
                        // Updater.check 内部已兜底网络异常（CancellationException 会照常抛出）
                        val outcome = Updater.check(App.api)
                        checking = false
                        when (outcome) {
                            is CheckResult.Success -> {
                                val info = outcome.info
                                if (info.available && info.release != null) {
                                    App.updateInfo.value = info
                                } else {
                                    toast(
                                        context,
                                        info.message.ifBlank {
                                            "已是最新版本 " + Constants.APP_VERSION
                                        },
                                    )
                                }
                            }
                            is CheckResult.Failure -> toast(context, outcome.message)
                        }
                    }
                },
            )
            Muted("妖精论坛 Android 客户端。Web / Windows / Android 三端共用同一套服务端接口与主题色板。")
        }

        // ── 支持作者（常驻赞赏码入口）──
        // 入口常驻可见；图片由 Coil 加载并落盘缓存，不需要每次重新下载。
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionTitle("支持作者")
            Muted(
                "妖精论坛是纯公益的粉丝二创项目，服务器与开发全凭热爱维持。如果它帮到了你，请我喝杯奶茶就好～",
                maxLines = 4,
            )
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                AsyncImage(
                    model = Constants.REWARD_QR_URL,
                    contentDescription = "作者赞赏码",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier
                        .width(200.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(colors.bgInput),
                )
            }
            Muted("扫码即可赞赏，金额随意，感谢每一位支持者。", maxLines = 2)
        }

        // ── 快捷入口 ──
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(colors.bgCard)
                .padding(4.dp),
        ) {
            SettingEntry("搜索帖子与用户") { nav.push(Screen.Search()) }
            SettingEntry("发布新帖子") { nav.push(Screen.PostCreate()) }
            SettingEntry("访问 WIKI") { nav.switchTab(Screen.Wiki) }
            SettingEntry("进入世界频道") { nav.switchTab(Screen.World) }
        }

        EmptyBox("妖精论坛 · 三端同步")
    }
}

@Composable
private fun SettingEntry(text: String, onClick: () -> Unit) {
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

/** 展示当前年制下的时间样例，方便用户判断。 */
@Composable
private fun ExampleYearRow() {
    val colors = ForumTheme.colors
    val sample = remember(App.yearMode.value) {
        val cal = java.util.Calendar.getInstance()
        TimeFmt.yearText(cal.get(java.util.Calendar.YEAR)) + "-01-01 00:00"
    }
    Text(
        text = "示例：现在的年份显示为 $sample",
        color = colors.textMuted,
        fontSize = 12.sp,
    )
}
