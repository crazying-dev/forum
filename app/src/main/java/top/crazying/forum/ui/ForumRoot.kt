package top.crazying.forum.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import top.crazying.forum.core.App
import top.crazying.forum.core.Updater
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.screens.AuthScreen
import top.crazying.forum.ui.screens.EasterEggScreen
import top.crazying.forum.ui.screens.ForumScreen
import top.crazying.forum.ui.screens.HomeScreen
import top.crazying.forum.ui.screens.MeScreen
import top.crazying.forum.ui.screens.PostCreateScreen
import top.crazying.forum.ui.screens.PostDetailScreen
import top.crazying.forum.ui.screens.SearchScreen
import top.crazying.forum.ui.screens.UserScreen
import top.crazying.forum.ui.screens.WikiScreen
import top.crazying.forum.ui.screens.WorldScreen

/**
 * 应用根节点：持有回退栈、渲染当前页，并在 tab 根页显示底部导航。
 *
 * insets 策略：最外层 Scaffold 刻意关掉 contentWindowInsets（`WindowInsets(0,0,0,0)`），
 * 由各页面自行用 `statusBarsPadding()` / `navigationBarsPadding()` / `imePadding()` 处理，
 * 这样 WIKI（全屏 WebView）等页面可以自行决定是否让内容顶到状态栏。
 */
@Composable
fun ForumRoot() {
    ForumTheme {
        val nav = remember { Navigator() }
        val colors = ForumTheme.colors

        // 启动时若本地存有会话（cookie + 用户缓存），静默刷新一次当前用户。
        // 失败（如 cookie 失效）由 Api 内部触发 onUnauthorized 清理，不打扰用户。
        LaunchedEffect(Unit) {
            if (App.prefs.userJson.isNotBlank()) {
                runCatching { App.api.me() }
            }
            // 冷启动静默检查更新：距上次检查不足 24 小时会被 `autoCheck` 跳过；
            // 只有确实发现新版本时才写入状态，弹窗交给 UpdateDialogHost。
            runCatching { Updater.autoCheck(App.api) }.getOrNull()?.let {
                App.updateInfo.value = it
            }
        }

        BackHandler(enabled = nav.canGoBack) { nav.pop() }

        Scaffold(
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
            containerColor = colors.bgBody,
            bottomBar = {
                if (nav.isTabRoot) {
                    NavigationBar(containerColor = colors.bgHeader) {
                        BOTTOM_TABS.forEach { tab ->
                            val selected = nav.current == tab.screen
                            NavigationBarItem(
                                selected = selected,
                                onClick = { nav.switchTab(tab.screen) },
                                icon = {
                                    Icon(
                                        imageVector = tabIcon(tab.screen),
                                        contentDescription = tab.label,
                                    )
                                },
                                label = { Text(tab.label) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = colors.primary,
                                    selectedTextColor = colors.primary,
                                    indicatorColor = colors.bgInput,
                                    unselectedIconColor = colors.textMuted,
                                    unselectedTextColor = colors.textMuted,
                                ),
                            )
                        }
                    }
                }
            },
        ) { padding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                when (val s = nav.current) {
                    Screen.Home -> HomeScreen(nav)
                    Screen.Forum -> ForumScreen(nav)
                    Screen.World -> WorldScreen(nav)
                    Screen.Wiki -> WikiScreen()
                    Screen.EasterEgg -> EasterEggScreen(nav)
                    Screen.Me -> MeScreen(nav)
                    is Screen.PostDetail -> PostDetailScreen(nav, s.postId)
                    is Screen.PostCreate -> PostCreateScreen(nav, s.category)
                    is Screen.Search -> SearchScreen(nav, s.keyword)
                    is Screen.UserProfile -> UserScreen(nav, s.userId)
                    is Screen.Auth -> AuthScreen(nav, s.register)
                }

                // 发现新版本时由 App.updateInfo 驱动弹出（冷启动自动检查 / 设置页手动检查）
                UpdateDialogHost()
            }
        }
    }
}

/** 底部 tab 图标（仅使用 Material 核心图标库，避免额外依赖）。 */
private fun tabIcon(screen: Screen): ImageVector = when (screen) {
    Screen.Home -> Icons.Default.Home
    Screen.Forum -> Icons.AutoMirrored.Filled.List
    Screen.World -> Icons.Default.Send
    Screen.Wiki -> Icons.Default.Info
    Screen.EasterEgg -> Icons.Default.Star
    else -> Icons.Default.Person
}
