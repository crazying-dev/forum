// ── 妖精论坛 · Android 客户端（V1.0.0-Beta）────────────────────────────
// 版本基线（均取自 Maven 元数据的当前最新稳定版，可用 tools/check-versions.ps1 复查）：
//   AGP 8.13.2 / Gradle 8.14.5 / Kotlin 2.4.20 / Compose BOM 2026.09.00
// 说明：AGP 9.x 已改为「内置 Kotlin」（需去掉 org.jetbrains.kotlin.android 并改用新 DSL），
//       本项目先锁定在成熟稳定的 8.x 线，升级路径见 README「七、后续计划」。
plugins {
    id("com.android.application") version "8.13.2" apply false
    id("org.jetbrains.kotlin.android") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
}
