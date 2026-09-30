package top.crazying.forum

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import top.crazying.forum.ui.ForumRoot

/**
 * 唯一 Activity：全部界面由 Compose 绘制，导航是自实现的单 Activity 回退栈（见 `ui/AppNav.kt`）。
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // targetSdk 35+ 系统强制 edge-to-edge，这里显式开启，让各页面自己处理 insets。
        enableEdgeToEdge()
        setContent { ForumRoot() }
    }
}
