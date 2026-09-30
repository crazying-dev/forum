# 妖精论坛 · Android 客户端

原生 **Kotlin + Jetpack Compose** 重写版，与 Web 端（`forum`）和 Windows 端（`forum-windows`）共用同一套服务端与主题色板。

| 项 | 值 |
| --- | --- |
| 当前版本 | **V1.0.0-Beta**（`versionCode = 1`） |
| 分支 | `Android` |
| 包名 | `top.crazying.forum`（debug 后缀 `.debug`） |
| 服务端 | `https://www.yjlt.top` |
| 最低 / 目标 SDK | 24（Android 7.0） / 36（Android 16） |

> 本目录是 **从零重写** 的原生工程：旧 PyQt6 移植版已整体移除，不再保留任何 Python 代码。

---

## 一、技术选型

| 层面 | 选型 | 说明 |
| --- | --- | --- |
| 语言 / UI | Kotlin 2.4.20 + Jetpack Compose（Material 3） | 单 Activity + 自实现回退栈 |
| 导航 | 自写 `Navigator`（`ui/AppNav.kt`） | 有意 **不引入** `navigation-compose`，避免导航库与 Compose 版本绑定带来的升级风险 |
| 网络 | OkHttp 5.5.0（手写 `Api` / `ApiResult`） | 仅一个出网入口；Cookie 持久化由 `PrefsCookieJar` 完成 |
| JSON | `org.json`（Android 内置） | 不引入 Gson / Moshi / kotlinx-serialization，减少依赖面 |
| 图片 | Coil 3（`coil-compose` + `coil-network-okhttp`） | 头像加载 |
| 正文渲染 | `AndroidView` + `TextView` + `HtmlCompat` | 服务端正文存的是 HTML |
| WebView | **仅用于 WIKI 页** | 其余界面全部 Compose |

**版本基线**（均取 Maven 元数据的当前稳定版，见 `build.gradle.kts` 注释）：

```
AGP 8.13.2  /  Gradle 8.14.5  /  Kotlin 2.4.20  /  Compose BOM 2026.09.00
core-ktx 1.19.1  /  activity-compose 1.13.0  /  lifecycle 2.11.0
coil3 3.6.3  /  okhttp 5.5.0  /  kotlinx-coroutines 1.11.0
```

> **为什么不直接上 AGP 9.x？** AGP 9 已改为「内置 Kotlin」（需要删掉 `org.jetbrains.kotlin.android` 插件并改用新的 Compose 开关 DSL）。为降低首次构建失败的概率，本轮锁定在成熟的 8.x 线；升级路线见「六、后续计划」。

---

## 二、三端一致性

### 主题

| 偏好（可手动选择） | 平日 | 国庆假期内（10-01 00:00 ~ 10-07 24:00） |
| --- | --- | --- |
| 浅色 `day` | 浅色 | **国庆浅色**（暖白米底 + 中国红 + 五星金） |
| 深色 `night` | 深色 | **国庆深色**（暗红底 + 亮金） |
| 跟随系统 `auto` | 跟随系统深浅色 | **恒为国庆浅色** |

* 国庆浅/深属于 **假期内的强制叠加层**：设置页里看不到、不可手动选择，也 **不会** 写进 `SharedPreferences`；落盘的永远是基础值 `day` / `night` / `auto`。
* 色板 28 个色值与 `forum-windows/app/theme.py` 的 `PALETTES`、Web 端 `static/css/main.css` 逐项对齐。
* 状态栏 / 导航栏颜色与图标明暗会随主题同步（与 Web 端 `theme-color` 同义）。
* **与另两端的差异**：`auto` 在 Android 上取「跟随系统深色模式」（`isSystemInDarkTheme()`），而 Web / Windows 用「按小时切换」。这是有意的平台化取舍。

### 年制

`无限年 = 公元年 − 1604`（无限元年 = 公元 1604 年）；公元年 < 1604 时显示「无限前 N 年」。影响帖子 / 评论 / 注册时间的年份显示。

### 接口

全部走 `https://www.yjlt.top` 的 HTTPS 接口，与 Windows 端 `app/api.py` 完全同源：

```
认证   POST /api/user/login | /api/user/logout | /api/user/register
       GET  /api/user/info        PUT /api/user/info
帖子   GET  /api/posts | /api/posts/random | /api/posts/<id>
       POST /api/posts/create | /api/posts/<id>/like | /favorite | /delete
评论   GET  /api/posts/<id>/comments        POST .../comments/create
用户   GET  /api/user/<id> | /posts | /favorites | /comments | /following | /followers
       POST /api/user/<id>/follow
搜索   GET  /api/search
世界   GET  /api/world/ALL             POST /api/world/Send
```

---

## 三、目录结构

```
forum-Android/
├── gradlew / gradlew.bat                  Gradle Wrapper（已入库）
├── gradle/wrapper/gradle-wrapper.jar      Wrapper 引导 jar（官方 8.14.5，sha256 已校验）
├── build.gradle.kts                       插件版本（apply false）
├── settings.gradle.kts                    仓库与模块声明
├── gradle.properties
├── tools/setup-android-env.ps1            环境安装脚本（JDK 17 + Android SDK）
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml
        ├── res/values{,night}/             名字、颜色、主题、图标
        └── java/top/crazying/forum/
            ├── ForumApp.kt                 Application，初始化单例
            ├── MainActivity.kt             单 Activity
            ├── core/
            │   ├── Constants.kt            服务端地址 / 版本 / 国庆区间 / 年制 / 分类表
            │   ├── Prefs.kt                SharedPreferences 封装
            │   ├── App.kt                  进程级单例（可被 Compose 观察的状态）
            │   ├── Http.kt                 PrefsCookieJar
            │   ├── Api.kt                  ApiResult + Api（全部接口）
            │   └── TimeFmt.kt              年制 / 相对时间 / 生日 / 去 HTML
            ├── theme/
            │   ├── Palette.kt              4 套色板（各 28 键）
            │   └── Theme.kt                ThemeMode / ThemeResolver / ForumTheme
            ├── data/Models.kt              Post / CommentItem / UserItem / WorldMessage
            └── ui/
                ├── AppNav.kt               Screen / Tab / Navigator
                ├── ForumRoot.kt            根节点：回退栈 + 底部导航
                ├── components/             通用控件（卡片、按钮、头像、正文…）
                └── screens/                11 个页面
```

---

## 四、构建

### 1. 安装环境（只需一次）

```powershell
# 在仓库根目录执行
powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup-android-env.ps1
```

脚本做的事（全部幂等，已存在的会跳过）：

1. 查找 / 安装 **JDK 17**（优先复用 `JAVA_HOME`、`Program Files` 下已有的 JDK 17；找不到则 `winget install Microsoft.OpenJDK.17`）
2. 下载并解压 **Android SDK 命令行工具**（`commandlinetools-win-16111833_latest.zip`，约 155 MB）→ `<SDK>\cmdline-tools\latest`
3. 自动接受许可证并安装 `platform-tools`、`platforms;android-36`、`build-tools;36.0.0`
4. 写出 `local.properties`（`sdk.dir=…`，已 git-ignore）
5. 把 `JAVA_HOME` / `ANDROID_HOME` / `ANDROID_SDK_ROOT` 写入**用户级**环境变量

常用开关：`-SdkRoot <path>`、`-JdkHome <path>`、`-SkipJdk`、`-SkipSdk`、`-NoPersistEnv`。

> 若 `winget` 不可用，脚本会提示手动下载 JDK 17，然后用 `-JdkHome <path>` 重跑。
> SDK 下载总量约 500 MB，请确认能访问 `dl.google.com`。

安装完 **请新开一个终端**（让环境变量生效）。

### 2. 构建 APK

```powershell
.\gradlew.bat assembleDebug        # 产物 app\build\outputs\apk\debug\app-debug.apk
.\gradlew.bat assembleRelease      # 未开启混淆 / 未签名
```

首次构建会自动下载 Gradle 8.14.5（约 138 MB）到 `%USERPROFILE%\.gradle`。

已安装 Android Studio 的话，直接打开本目录即可（Studio 自带的 JDK 也能满足要求，但请确认 Gradle JDK 为 17）。

### 3. 装到设备

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

---

## 五、本轮已实现 / 未实现

### 已实现（V1.0.0-Beta）

* **账号**：登录（用户名或邮箱）、注册（用户名 + 邮箱 + 密码直注）、退出登录、本地会话恢复与失效清理
* **首页**：最新发布 / 综合排序 / 随机推荐 / 我的收藏 四个信息流，分页加载
* **论坛**：全部 + 5 个分类（综合 / 闲聊 / 求助 / 分享 / 创作），分页加载
* **帖子详情**：作者信息、HTML 正文、点赞 / 收藏、评论列表（一层回复缩进）、发评论、回复指定评论
* **发帖**：分类选择、标题（≤ 100 字）、正文；纯文本按空行分段转 HTML（转义 `& < >`，不做 HTML 注入）
* **搜索**：帖子 + 用户，支持「全部 / 帖子 / 用户」筛选
* **用户主页**：资料卡、关注 / 已关注、帖子 / 收藏 / 评论三个列表
* **世界频道**：`/api/world/ALL` + 20 秒轮询、发送消息、头像可点进个人主页
* **WIKI**：WebView 加载 `/WIKI`
* **我的 / 设置**：主题（浅色 / 深色 / 跟随系统）、年制（无限年 / 公元年，含示例）、版本 / 服务端 / 客户端标识、快捷入口
* **主题**：4 套色板 + 国庆假期强制叠加（与 Web / Windows 三端同语义）

### 未实现（后续多轮持续补齐）

头像上传、修改密码 / 邮箱、邮箱验证码注册、彩蛋、会馆、举报 / 删除内容、收藏独立页、Live2D 桌宠、鼠标指针、深链、世界频道 WebSocket（当前为轮询）、正文内联图片渲染、富文本编辑器。

---

## 六、后续计划

1. **补齐上述未实现功能**，优先顺序：邮箱验证码注册 → 修改密码 / 邮箱 → 头像上传 → 删除 / 举报 → 收藏独立页。
2. **世界频道升级为 WebSocket**（当前 20 秒轮询，服务端对发送有 2 秒 / 人 限流）。
3. **正文内联图片**：`HtmlBody` 目前会剥离 `<img>`，可换成 Coil + `ImageGetter`。
4. **AGP 9.x 升级**：用 Android Studio 的 AGP Upgrade Assistant 迁移（删除 `org.jetbrains.kotlin.android`，改用内置 Kotlin DSL），并同步升级 Gradle。
5. **签名与发布**：`keystore.properties` + `signingConfigs`，产出已签名 release APK / AAB。

---

## 七、已知限制与注意事项

* **WIKI 页使用 WebView**，这是本工程唯一的 WebView 使用点；其余界面均为 Compose 原生控件。
* **正文内联图片不显示**：`HtmlBody` 主动剥离 `<img>` / `<script>`，只保留文字、段落、粗体、链接、代码块等常用标签。
* **`auto` 主题语义**：Android 取「跟随系统深色模式」，与 Web / Windows 的「小时切换」不同（有意为之）。
* **Coil 3 的网络加载器**：依赖 `coil-network-okhttp` 的 ServiceLoader 自动注册；若自定义 `ImageLoader` 需手动装配 `OkHttpNetworkFetcherFactory`。
* **头像无占位图**：URL 为空时渲染「猫」字占位，尚未接入错误 / 占位 painter。
* **服务端不可达时**：`Api` 对 GET 请求重试 1 次（写操作绝不重试，避免重复发帖 / 评论）；返回 401 会静默清理本地会话。
* **`local.properties` 严禁入库**（已在 `.gitignore` 中）；`gradle-wrapper.jar` 相反 **必须入库**。
* **签名材料**（`*.jks` / `*.keystore` / `keystore.properties`）同样已 git-ignore。
* 本工程源码是在 **无 JDK / 无 SDK 环境** 下编写的，尚未经过真实编译；若首次构建报错，请把完整日志反馈回来（预期仅需小幅修正）。
