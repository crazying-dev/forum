import java.io.File
import java.util.Properties

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// ── 版本号唯一真相源 ──
// 改版本只改 appVersionName 这一行：versionCode 与 BuildConfig.APP_VERSION 均由此派生，
// 再由 Constants.APP_VERSION 读 BuildConfig，全工程不再有第二份版本字面量。
val appVersionName = "1.1.0"
// 允许预发布后缀（如 1.2.0-beta1）：versionCode 只取数字基段，versionName 保留完整串。
val appVersionBase = appVersionName.substringBefore('-').substringBefore('+')
val parts = appVersionBase.split(".").map { it.toIntOrNull() ?: error("versionName 非法：$appVersionName") }
require(parts.size == 3) { "versionName 必须是 major.minor.patch[-suffix]：$appVersionName" }
val appVersionCode = parts[0] * 10000 + parts[1] * 100 + parts[2]
// CI 发布时可用 -PexpectedVersion=<tag 版本> 校验 tag 与源码里的版本一致，本地构建可不传。
val expectedVersion = (findProperty("expectedVersion") as String?)?.trim().orEmpty()
require(expectedVersion.isEmpty() || expectedVersion == appVersionName) { "tag 版本 $expectedVersion 与 versionName $appVersionName 不一致" }

android {
    namespace = "top.crazying.forum"
    compileSdk = 36

    defaultConfig {
        applicationId = "top.crazying.forum"
        minSdk = 24
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersionName
        // 供 Constants.APP_VERSION 读取，保证运行时版本号与构建版本同源。
        buildConfigField("String", "APP_VERSION", "\"$appVersionName\"")
        // 中文优先即可，服务端只返回中文文案
        resourceConfigurations += listOf("zh", "en")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // 默认生产基址；本地联调可用 -PapiBaseUrl=http://10.0.2.2:8090 覆盖（仅调试构建使用）。
        val apiBaseUrl = (project.findProperty("apiBaseUrl") as String?)?.trim().orEmpty()
            .ifBlank { "https://www.yjlt.top" }
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }

    // 发布签名：环境变量优先（CI 注入），仓库根 keystore.properties 兜底（本地旧用法，兼容保留）。
    // 四项凭据齐备且 keystore 文件存在才创建 release 签名配置；否则 release 产出未签名包，
    // 不让无凭据的 CI / 克隆构建失败。
    val keystorePropsFile = rootProject.file("keystore.properties")
    val keystoreProps = Properties().apply {
        if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
    }
    val releaseStoreFileRaw = System.getenv("ANDROID_KEYSTORE_FILE")?.trim()?.takeIf { it.isNotEmpty() }
        ?: keystoreProps.getProperty("storeFile")
    val releaseStorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")?.trim()?.takeIf { it.isNotEmpty() }
        ?: keystoreProps.getProperty("storePassword")
    val releaseKeyAlias = System.getenv("ANDROID_KEY_ALIAS")?.trim()?.takeIf { it.isNotEmpty() }
        ?: keystoreProps.getProperty("keyAlias")
    val releaseKeyPassword = System.getenv("ANDROID_KEY_PASSWORD")?.trim()?.takeIf { it.isNotEmpty() }
        ?: keystoreProps.getProperty("keyPassword")
    // 相对路径按仓库根解析（与旧 keystore.properties 里的相对写法一致）。
    val releaseStoreFile = releaseStoreFileRaw?.trim()?.takeIf { it.isNotEmpty() }?.let { path ->
        if (File(path).isAbsolute) File(path) else rootProject.file(path)
    }
    val hasReleaseKey = releaseStoreFile?.exists() == true &&
        !releaseStorePassword.isNullOrBlank() &&
        !releaseKeyAlias.isNullOrBlank() &&
        !releaseKeyPassword.isNullOrBlank()

    signingConfigs {
        if (hasReleaseKey) {
            create("release") {
                storeFile = releaseStoreFile
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (hasReleaseKey) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    // 版本选择依据：AGP 8.13.2 + compileSdk 36 上限（参见根 build.gradle.kts 注释）
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.1")

    implementation(platform("androidx.compose:compose-bom:2025.08.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")

    implementation("io.coil-kt.coil3:coil-compose:3.2.0")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.2.0")
    implementation("com.squareup.okhttp3:okhttp:5.0.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    debugImplementation("androidx.compose.ui:ui-tooling")

    // 纯 Kotlin 逻辑（如 MarkdownBody）的 JVM 单元测试
    testImplementation("junit:junit:4.13.2")
    // org.json 在 Android 运行时由系统提供，JVM 单测需要显式依赖
    testImplementation("org.json:json:20240303")

    // Compose UI 测试（跨段选区 / 编辑器 / ALTCHA 遮罩）
    androidTestImplementation(platform("androidx.compose:compose-bom:2025.08.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
