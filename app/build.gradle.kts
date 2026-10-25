import java.util.Properties

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "top.crazying.forum"
    compileSdk = 36

    defaultConfig {
        applicationId = "top.crazying.forum"
        minSdk = 24
        targetSdk = 36
        versionCode = 20
        versionName = "1.1.0"
        // 中文优先即可，服务端只返回中文文案
        resourceConfigurations += listOf("zh", "en")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // 默认生产基址；本地联调可用 -PapiBaseUrl=http://10.0.2.2:8090 覆盖（仅调试构建使用）。
        val apiBaseUrl = (project.findProperty("apiBaseUrl") as String?)?.trim().orEmpty()
            .ifBlank { "https://www.yjlt.top" }
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }

    // 发布签名：凭据放在仓库根的 keystore.properties（已 gitignore，不入库）。
    // 文件缺失时 release 回退为未签名产物，方便无凭据的 CI / 克隆直接 assembleDebug。
    val keystorePropsFile = rootProject.file("keystore.properties")
    val hasReleaseKey = keystorePropsFile.exists()

    signingConfigs {
        if (hasReleaseKey) {
            create("release") {
                val props = Properties().apply {
                    keystorePropsFile.inputStream().use { load(it) }
                }
                storeFile = rootProject.file(props.getProperty("storeFile"))
                storePassword = props.getProperty("storePassword")
                keyAlias = props.getProperty("keyAlias")
                keyPassword = props.getProperty("keyPassword")
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
