// ── 妖精论坛 · Android 客户端（V1.0.8）────────────────────────────
// 版本基线（已通过真实构建验证；AGP 8.13.2 + compileSdk 36 组合）：
//   AGP 8.13.2 / Gradle 8.14.5 / Kotlin 2.2.20 / Compose BOM 2025.08.00
//
// 为什么不直接用最新依赖：core-ktx 1.19.1、Compose 1.12.x（BOM 2026.09.00）、
// okhttp 5.5.0、coil3 3.6.3 等新版在 AAR 元数据里要求
//   「AGP >= 9.1.0 且 compileSdk >= 37」，
// 而 AGP 9.x 已改为「内置 Kotlin」（需去掉 org.jetbrains.kotlin.android 并切新 DSL）。
// 升级路径见 README「六、后续计划」。
plugins {
    id("com.android.application") version "8.13.2" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.20" apply false
}
