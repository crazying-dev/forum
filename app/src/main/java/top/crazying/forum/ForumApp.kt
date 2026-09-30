package top.crazying.forum

import android.app.Application
import top.crazying.forum.core.App

/**
 * 应用入口：只负责在最早的时机初始化进程级单例（SharedPreferences / HTTP 客户端）。
 *
 * AndroidManifest 里 `android:name=".ForumApp"` 指向本类；缺少本类会在启动瞬间崩溃。
 */
class ForumApp : Application() {

    override fun onCreate() {
        super.onCreate()
        App.init(this)
    }
}
