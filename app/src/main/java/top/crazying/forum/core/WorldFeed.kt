package top.crazying.forum.core

/**
 * 世界频道的展示顺序（纯逻辑，便于 JVM 单测）。
 *
 * 服务端 `db.world.get_world_messages()` 是 `ORDER BY created_at DESC`，
 * 也就是**最新在前**；而聊天窗口要的是「早的在上、最新在下」，让新消息
 * 贴在底部输入框上方。转换口径集中在这里，避免各处各写一遍再写反。
 */
object WorldFeed {

    /**
     * 倒序列表（最新在前）→ 聊天顺序（最新在后），且只保留最新的 [limit] 条。
     *
     * 注意是 `take(limit)` 而不是 `takeLast(limit)`：列表头部才是新的。
     *
     * @param limit ≤ 0 表示不截断
     */
    fun <T> newestLast(descRows: List<T>, limit: Int): List<T> {
        if (descRows.isEmpty()) return emptyList()
        val head = if (limit > 0) descRows.take(limit) else descRows
        return head.reversed()
    }
}
