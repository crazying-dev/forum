package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * V1.0.10 新增：本地缓存「最多 24 小时」统一策略（[CachePolicy]）的 JVM 单测。
 *
 * 固定时间戳 + 显式设置 mtime，不依赖系统时钟，避免跨时区 / 跨天波动。
 */
class CachePolicyTest {

    /** 固定基准时间（ms）。 */
    private val now = 1_800_000_000_000L

    private fun tempDir(): File =
        Files.createTempDirectory("crforum-policy").toFile()

    @Test
    fun maxAgeIs24Hours() {
        assertEquals(24L * 60 * 60 * 1000, CachePolicy.MAX_AGE_MS)
        assertEquals(86_400_000L, CachePolicy.MAX_AGE_MS)
    }

    @Test
    fun isStaleTimestampBoundaries() {
        assertFalse(CachePolicy.isStale(now, now))
        assertFalse(CachePolicy.isStale(now - CachePolicy.MAX_AGE_MS, now))       // 恰好 24h 不算过期
        assertTrue(CachePolicy.isStale(now - CachePolicy.MAX_AGE_MS - 1, now))
        assertFalse(CachePolicy.isStale(0L, now))                                 // 无时间信息
        assertFalse(CachePolicy.isStale(-1L, now))
    }

    @Test
    fun isStaleFileUsesLastModified() {
        val dir = tempDir()
        try {
            val fresh = File(dir, "fresh.png").apply {
                writeBytes(byteArrayOf(1))
                setLastModified(now)
            }
            assertFalse(CachePolicy.isStaleFile(fresh, now))

            val expired = File(dir, "old.png").apply {
                writeBytes(byteArrayOf(1))
                setLastModified(now - CachePolicy.MAX_AGE_MS - 1_000)
            }
            assertTrue(CachePolicy.isStaleFile(expired, now))

            assertFalse(CachePolicy.isStaleFile(File(dir, "missing.png"), now))  // 不存在 ≠ 过期
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun imageCacheDirIsBucketedBy24Hours() {
        val base = File("base")
        val current = CachePolicy.imageCacheDir(base, now)
        val soon = CachePolicy.imageCacheDir(base, now + 1)
        val nextDay = CachePolicy.imageCacheDir(base, now + CachePolicy.MAX_AGE_MS)

        assertEquals(CachePolicy.bucketOf(now).toString(), current.name)
        assertEquals(current, soon)                       // 同一时段内目录稳定
        assertNotEquals(current, nextDay)                 // 跨时段换目录
        assertEquals(current.parentFile, base)
    }

    @Test
    fun pruneOldBucketsKeepsCurrentOnly() {
        val base = tempDir()
        try {
            val keep = CachePolicy.imageCacheDir(base, now).apply { mkdirs() }
            File(keep, "a.0").writeBytes(byteArrayOf(1))
            val older = CachePolicy.imageCacheDir(base, now - CachePolicy.MAX_AGE_MS).apply { mkdirs() }
            File(older, "b.0").writeBytes(byteArrayOf(1))

            assertEquals(1, CachePolicy.pruneOldBuckets(base, now))
            assertTrue(keep.exists())
            assertTrue(File(keep, "a.0").exists())
            assertFalse(older.exists())
            assertEquals(0, CachePolicy.pruneOldBuckets(base, now))   // 再清一次无副作用
        } finally {
            base.deleteRecursively()
        }
    }

    @Test
    fun pruneStaleFilesRemovesExpiredOnly() {
        val dir = tempDir()
        try {
            val fresh = File(dir, "fresh.apk").apply {
                writeBytes(byteArrayOf(1))
                setLastModified(now)
            }
            val expired = File(dir, "old.apk").apply {
                writeBytes(byteArrayOf(1))
                setLastModified(now - CachePolicy.MAX_AGE_MS - 1_000)
            }

            assertEquals(1, CachePolicy.pruneStaleFiles(dir, now))
            assertTrue(fresh.exists())
            assertFalse(expired.exists())
            assertEquals(0, CachePolicy.pruneStaleFiles(dir, now))
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun pruneOnMissingDirIsNoop() {
        val missing = File(tempDir(), "not-there")
        assertEquals(0, CachePolicy.pruneOldBuckets(missing, now))
        assertEquals(0, CachePolicy.pruneStaleFiles(missing, now))
    }
}
