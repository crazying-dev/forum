package top.crazying.forum.core

import java.io.File

/**
 * 本地缓存统一时效策略：任何本地持久缓存**最多保留 24 小时**（V1.0.10）。
 *
 * 统一口径（用户资料缓存 / 图片缓存 / 更新包缓存一致）：
 *
 * * **上限 24 小时**：每条本地缓存都带时间信息（时间戳或文件 mtime），
 *   超过 [MAX_AGE_MS] 即视为「过期」；
 * * **过期先用旧数据**：过期不妨碍使用——先把旧数据渲染出来（秒开、离线可用），
 *   随后在后台静默重新拉取，拿到新数据后再覆盖缓存；
 * * **失败保留旧数据**：刷新失败（离线 / 4xx / 5xx）一律保留旧缓存，不清空。
 *
 * 纯 Kotlin 实现（只依赖 `java.io.File`），可直接跑 JVM 单元测试。
 */
object CachePolicy {

    /** 本地缓存最多保留多久：24 小时（毫秒）。 */
    const val MAX_AGE_MS: Long = 24L * 60 * 60 * 1000

    /** 时间戳落在哪一个 24 小时时段（Unix 纪元起的第几个 24 小时）。 */
    fun bucketOf(nowMs: Long = System.currentTimeMillis()): Long = nowMs / MAX_AGE_MS

    /** 时间戳是否已超过 [MAX_AGE_MS]；`<= 0` 表示「没有时间信息」，不算过期。 */
    fun isStale(stampMs: Long, nowMs: Long = System.currentTimeMillis()): Boolean {
        if (stampMs <= 0L) return false
        return nowMs - stampMs > MAX_AGE_MS
    }

    /** 文件的 mtime 是否已超过 [MAX_AGE_MS]；文件不存在返回 `false`。 */
    fun isStaleFile(file: File, nowMs: Long = System.currentTimeMillis()): Boolean {
        if (!file.exists()) return false
        return isStale(file.lastModified(), nowMs)
    }

    /**
     * 图片磁盘缓存目录：按 24 小时时段分桶（`baseDir/<时段号>`）。
     *
     * 换时段后旧目录整体作废（见 [pruneOldBuckets]），因此任何图片最多被使用 24 小时。
     */
    fun imageCacheDir(baseDir: File, nowMs: Long = System.currentTimeMillis()): File =
        File(baseDir, bucketOf(nowMs).toString())

    /**
     * 删除 [baseDir] 下不属于当前时段的子目录，返回删除数量。
     *
     * 只在 App 启动、Coil 单例创建之前调用，因此不会删到正在使用的缓存。
     */
    fun pruneOldBuckets(baseDir: File, nowMs: Long = System.currentTimeMillis()): Int {
        val keep = bucketOf(nowMs).toString()
        val children = baseDir.listFiles() ?: return 0
        var removed = 0
        for (child in children) {
            if (!child.isDirectory || child.name == keep) continue
            if (child.deleteRecursively()) removed++
        }
        return removed
    }

    /** 删除 [dir] 下 mtime 已超过 24 小时的文件，返回删除数量。 */
    fun pruneStaleFiles(dir: File, nowMs: Long = System.currentTimeMillis()): Int {
        val files = dir.listFiles() ?: return 0
        var removed = 0
        for (file in files) {
            if (isStaleFile(file, nowMs) && file.delete()) removed++
        }
        return removed
    }
}
