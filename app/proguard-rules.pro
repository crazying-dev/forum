# 保持 OkHttp / Kotlin 协程 / Coil 的反射入口（当前 release 未开启混淆，保留备用）
-keep class okhttp3.** { *; }
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class coil3.** { *; }
-dontwarn coil3.**
-keepclassmembers class kotlinx.coroutines.** { volatile <fields>; }
