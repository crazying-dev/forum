package top.crazying.forum.ui.screens

import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import top.crazying.forum.data.CommentItem
import top.crazying.forum.data.Post
import top.crazying.forum.data.UserItem

/**
 * 列表页需要「返回后保留」的状态：已加载内容、分页游标、滚动位置。
 *
 * 背景：本项目有意不使用 navigation-compose（见 [top.crazying.forum.ui.Navigator] 注释），
 * 根节点用 `when (nav.current)` 只渲染当前页，页面一旦被压栈（如进入帖子详情）
 * 就离开组合，页内 `remember` 的状态全部丢弃 —— 返回时列表被清空重载、滚动位置归零。
 *
 * 把状态放进根节点 `remember` 的 [FeedStateStore]（位于 `when` 之外）即可跨页面保留：
 * 返回时复用同一实例，滚动位置由 [listState] 记住。
 */
class FeedState(defaultFilter: String = "") {
    /** 首页：信息流 kind（latest / comprehensive / random / favorites）；论坛：分类 key（空串 = 全部）。 */
    var filter by mutableStateOf(defaultFilter)

    var posts by mutableStateOf<List<Post>>(emptyList())
    var page by mutableStateOf(1)
    var hasMore by mutableStateOf(false)
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")

    /** 已加载内容对应的标识；与当前标识一致时不再重载（从帖子详情返回即如此）。 */
    var loadedKey by mutableStateOf<String?>(null)

    /** 滚动位置：延迟创建，避免仅做逻辑测试时触碰 Compose foundation。 */
    val listState: LazyListState by lazy { LazyListState() }
}

/** 用户主页状态（资料卡 + 帖子 / 收藏 / 评论 三个列表）。 */
class UserFeedState {
    var user by mutableStateOf<UserItem?>(null)
    var profileLoading by mutableStateOf(true)
    var profileError by mutableStateOf("")
    var profileLoaded by mutableStateOf(false)

    var tab by mutableStateOf("posts")
    var loadedTab by mutableStateOf<String?>(null)
    var posts by mutableStateOf<List<Post>>(emptyList())
    var comments by mutableStateOf<List<CommentItem>>(emptyList())
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")

    val listState: LazyListState by lazy { LazyListState() }
}

/** 搜索页状态（关键词 / 类型 / 结果 / 滚动位置）。 */
class SearchState(keyword: String = "") {
    var keyword by mutableStateOf(keyword)
    var type by mutableStateOf("both")
    var posts by mutableStateOf<List<Post>>(emptyList())
    var users by mutableStateOf<List<UserItem>>(emptyList())
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")
    var searched by mutableStateOf(false)

    val listState: LazyListState by lazy { LazyListState() }
}

/**
 * 按 key 保留各列表页状态。
 *
 * 由 [top.crazying.forum.ui.ForumRoot] 用 `remember` 持有（位于导航 `when` 之外），
 * 因此从帖子详情返回列表页时 `of(...)` 仍返回同一实例，列表内容与滚动位置都还在。
 */
class FeedStateStore {
    private val feeds = mutableMapOf<String, FeedState>()
    private val users = mutableMapOf<String, UserFeedState>()
    private val searches = mutableMapOf<String, SearchState>()

    fun feed(key: String, defaultFilter: String = ""): FeedState =
        feeds.getOrPut(key) { FeedState(defaultFilter) }

    fun user(key: String): UserFeedState = users.getOrPut(key) { UserFeedState() }

    fun search(key: String): SearchState = searches.getOrPut(key) { SearchState(key) }
}

/**
 * 列表内容是否需要（重新）加载。
 *
 * 只有内容标识变化（切换信息流 / 分类 / 搜索词 / 用户主页）时才需要重新加载；
 * 从帖子详情返回时标识不变，直接复用已加载的数据与滚动位置。
 */
fun needReload(loadedKey: String?, currentKey: String): Boolean = loadedKey != currentKey
