package top.crazying.forum

import android.app.Application
import android.content.Context
import coil3.ImageLoader
import coil3.SingletonImageLoader
import coil3.disk.DiskCache
import coil3.disk.directory
import coil3.memory.MemoryCache
import top.crazying.forum.core.App
import top.crazying.forum.core.CachePolicy
import top.crazying.forum.core.Constants
import java.io.File

/**
 * 应用入口：最早时机初始化进程级单例（SharedPreferences / HTTP 客户端），
 * 并统一落地「本地缓存最多 24 小时」策略（V1.0.10，见 [CachePolicy]）。
 *
 * AndroidManifest 里 `android:name=".ForumApp"` 指向本类；缺少本类会在启动瞬间崩溃。
 */
class ForumApp : Application(), SingletonImageLoader.Factory {

    override fun onCreate() {
        super.onCreate()
        App.init(this)
        sweepLocalCaches()
    }

    /**
     * 启动清理：丢掉上一时段的图片磁盘缓存，并删除超过 24 小时的更新安装包。
     *
     * 必须在 Coil 单例创建之前执行，因此放在 `onCreate` 最前段。
     */
    private fun sweepLocalCaches() {
        runCatching {
            CachePolicy.pruneOldBuckets(File(cacheDir, Constants.IMAGE_CACHE_DIR))
            CachePolicy.pruneStaleFiles(File(cacheDir, Constants.UPDATE_DIR))
        }
    }

    /**
     * 自定义 Coil 单例：图片磁盘缓存按 24 小时时段分目录，启动时整体作废上一时段，
     * 因此任何图片最多缓存 24 小时（见 [CachePolicy.imageCacheDir]）。
     */
    override fun newImageLoader(context: Context): ImageLoader =
        ImageLoader.Builder(context)
            .memoryCache {
                MemoryCache.Builder()
                    .maxSizePercent(context, 0.25)
                    .build()
            }
            .diskCache {
                DiskCache.Builder()
                    .directory(
                        CachePolicy.imageCacheDir(
                            File(cacheDir, Constants.IMAGE_CACHE_DIR),
                        ),
                    )
                    .maxSizeBytes(IMAGE_DISK_CACHE_BYTES)
                    .build()
            }
            .build()

    private companion object {
        /** 图片磁盘缓存体积上限：64 MB（超出按最近使用淘汰）。 */
        const val IMAGE_DISK_CACHE_BYTES = 64L * 1024 * 1024
    }
}
