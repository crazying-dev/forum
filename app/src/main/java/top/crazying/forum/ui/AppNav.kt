package top.crazying.forum.ui

import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.snapshots.SnapshotStateList

/**
 * 页面声明。
 *
 * 有意不使用 `navigation-compose`：本项目只需一个线性回退栈，
 * 手写实现可以避开导航库与 Compose 版本绑定带来的升级风险（也更小）。
 */
sealed interface Screen {
    data object Home : Screen
    data object Forum : Screen
    data object World : Screen
    data object Wiki : Screen
    data object EasterEgg : Screen
    data object Me : Screen

    // 从「我的」页二级进入的普通页面（不占底部标签栏）。
    data object Privacy : Screen
    data object DeleteAccount : Screen
    data object ProfileEdit : Screen

    data class PostDetail(val postId: String) : Screen
    data class PostCreate(val category: String = "general") : Screen
    data class Search(val keyword: String = "") : Screen
    data class UserProfile(val userId: String) : Screen
    data class Auth(val register: Boolean = false) : Screen
}

/** 底部导航项。 */
data class Tab(val label: String, val screen: Screen)

val BOTTOM_TABS: List<Tab> = listOf(
    Tab("首页", Screen.Home),
    Tab("论坛", Screen.Forum),
    Tab("世界", Screen.World),
    Tab("WIKI", Screen.Wiki),
    Tab("彩蛋", Screen.EasterEgg),
    Tab("我的", Screen.Me),
)

/** 回退栈。栈深度为 1 时代表当前停在某个底部 tab 的根页（此时显示底部导航）。 */
class Navigator {

    val stack: SnapshotStateList<Screen> = mutableStateListOf(Screen.Home)

    val current: Screen get() = stack[stack.size - 1]

    val isTabRoot: Boolean get() = stack.size == 1

    val canGoBack: Boolean get() = stack.size > 1

    fun push(screen: Screen) {
        stack.add(screen)
    }

    fun pop(): Boolean {
        if (stack.size <= 1) return false
        stack.removeAt(stack.size - 1)
        return true
    }

    /** 切换底部 tab：直接重置栈。 */
    fun switchTab(screen: Screen) {
        if (stack.size == 1 && stack[0] == screen) return
        stack.clear()
        stack.add(screen)
    }
}
