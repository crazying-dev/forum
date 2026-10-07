# 妖精论坛 · Android 客户端

原生 **Kotlin + Jetpack Compose** 重写版，与 Web 端（`forum`）和 Windows 端（`forum-windows`）共用同一套服务端与主题色板。

| 项 | 值 |
| --- | --- |
| 当前版本 | **V1.0.15**（`versionCode = 16`） |
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
| WebView | **仅两处**：WIKI › Live2D 子页、网页端登录页（`/auth?mode=login`） | 其余界面（含 WIKI 其他子页）均为 Compose 原生绘制；人机验证虽仍用 WebView，但已改写为**页面内全屏遮罩**而非 Dialog |
| 应用更新 | 自写 `Updater`（`core/Updater.kt`） | 版本检查 → 三级回退下载 → sha256 校验 → FileProvider 调起系统安装器 |

**版本基线**（已通过真实构建验证）：

```
AGP 8.13.2  /  Gradle 8.14.5  /  Kotlin 2.2.20  /  Compose BOM 2025.08.00
core-ktx 1.16.0  /  activity-compose 1.10.1  /  lifecycle 2.9.1
coil3 3.2.0  /  okhttp 5.0.0  /  kotlinx-coroutines 1.10.2
```

> **为什么不全用最新版？** 最新依赖（core-ktx 1.19.1、Compose BOM 2026.09.00 对应的 1.12.x、okhttp 5.5.0、coil3 3.6.3）在 AAR 元数据里要求 **AGP ≥ 9.1.0 且 compileSdk ≥ 37**；而 AGP 9.x 已改为「内置 Kotlin」，需删掉 `org.jetbrains.kotlin.android` 并切换新的 Compose DSL。本项目先在成熟的 8.x 线上跑通，升级路线见「六、后续计划」。

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

### 图标

启动图标直接使用**原项目图标**（`forum/static/img/favicon.png`，1080×1080，与网站头部 / `apple-touch-icon`、Windows 端 `icon.ico` 同源），
由 `tools/gen-android-icons.ps1` 生成 `mipmap-*` 五档密度的方形 / 圆形图标，以及 API 26+ 自适应图标的前景层（背景层 `#FFFFFF`）。

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
彩蛋   GET  /Easter-Egg
更新   GET  /api/app/check?platform=android&version=<版本>
       GET  /api/app/mirror/android/<文件名>      （站内反代 GitHub 直链）
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
├── tools/gen-android-icons.ps1            图标生成脚本（原 logo → mipmap + 自适应图标）
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml
        ├── res/values{,night}/             名字、颜色、主题
        ├── res/mipmap-*/                   启动图标（原 logo 生成：方形 / 圆形 / 自适应前景）
        └── java/top/crazying/forum/
            ├── ForumApp.kt                 Application，初始化单例
            ├── MainActivity.kt             单 Activity
            ├── core/
            │   ├── Constants.kt            服务端地址 / 版本 / 国庆区间 / 年制 / 分类表
            │   ├── Prefs.kt                SharedPreferences 封装
            │   ├── App.kt                  进程级单例（可被 Compose 观察的状态）
            │   ├── Http.kt                 PrefsCookieJar
            │   ├── Api.kt                  ApiResult + Api（全部接口）
            │   ├── Updater.kt              自更新：检查 / 回退下载 / 校验 / 安装
            │   └── TimeFmt.kt              年制 / 相对时间 / 生日 / 去 HTML
            ├── theme/
            │   ├── Palette.kt              4 套色板（各 28 键）
            │   └── Theme.kt                ThemeMode / ThemeResolver / ForumTheme
            ├── data/Models.kt              Post / CommentItem / UserItem / WorldMessage
            └── ui/
                ├── AppNav.kt               Screen / Tab / Navigator
                ├── ForumRoot.kt            根节点：回退栈 + 底部导航
                ├── UpdateDialog.kt         「发现新版本」对话框（下载 / 校验 / 安装）
                ├── components/             通用控件（卡片、按钮、头像、正文…）
                └── screens/                12 个页面
```

---

## 四、构建

### 1. 安装环境（只需一次）

```powershell
# 在仓库根目录执行
powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup-android-env.ps1
```

脚本做的事（全部幂等，已存在的会跳过）：

1. 查找 / 安装 **JDK 17**：先复用 `JAVA_HOME`、`Program Files` 下已有的 JDK 17；找不到则 `winget install Microsoft.OpenJDK.17`（已固定 `--source winget`，避开证书有问题的 `msstore` 源）；**winget 不可用或失败时自动回退到无需管理员的便携版 zip**（解压到 `%LOCALAPPDATA%\Programs\Microsoft\jdk-17*`）
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
.\gradlew.bat assembleRelease      # 未开启混淆；存在 keystore.properties 时自动签名
```

首次构建会自动下载 Gradle 8.14.5（约 138 MB）到 `%USERPROFILE%\.gradle`。

> ⚠️ **国内网络注意**：`services.gradle.org` 可能超时（本机实测过），导致卡在 `Downloading https://services.gradle.org/distributions/gradle-8.14.5-bin.zip`。
> 若遇到，任选一种：
> 1. 已预置本地缓存（本机已完成），直接 `gradlew` 即可；
> 2. 手动下载后放进 Wrapper 缓存：
>    ```powershell
>    $u = 'https://mirrors.cloud.tencent.com/gradle/gradle-8.14.5-bin.zip'   # 腾讯云镜像
>    $d = "$env:USERPROFILE\.gradle\wrapper\dists\gradle-8.14.5-bin\690y85m0j9nfaub7xoiayko8a"
>    New-Item -ItemType Directory -Path $d -Force | Out-Null
>    Invoke-WebRequest $u -OutFile "$d\gradle-8.14.5-bin.zip"
>    # 官方 sha256: 6f74b601422d6d6fc4e1f9a1ab6522f642c2fdcbc15ae33ebd30ba3d7198e854
>    ```
> 3. 或把 `gradle/wrapper/gradle-wrapper.properties` 的 `distributionUrl` 换成镜像地址。

已安装 Android Studio 的话，直接打开本目录即可（Studio 自带的 JDK 也能满足要求，但请确认 Gradle JDK 为 17）。

### 3. 装到设备

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

---

## 五、本轮已实现 / 未实现

### 已实现（V1.0.13）

* **账号**：登录（用户名或邮箱）、注册（用户名 + 邮箱 + 密码直注）、退出登录、本地会话恢复与失效清理
* **首页**：最新发布 / 综合排序 / 随机推荐 / 我的收藏 四个信息流，分页加载
* **论坛**：全部 + 5 个分类（综合 / 闲聊 / 求助 / 分享 / 创作），分页加载
* **帖子详情**：作者信息、正文（**一律按 Markdown 渲染，不渲染 HTML 语法**：正文里的 HTML 标签按字面文字展示，与 Web / Windows 三端口径一致）、点赞 / 收藏（就地刷新，不重复计入浏览量）、楼中楼评论（两层：根 + 回复，深层压平并以「回复 @昵称」标注）、发评论 / 回复、删除自己的帖子 / 评论（二次确认）
* **发帖**：分类选择、标题（≤ 100 字）、正文；**正文原样直传服务端**（不做任何 HTML 包装 / 转义，与 Web / Windows 一致）
* **搜索**：帖子 + 用户，支持「全部 / 帖子 / 用户」筛选
* **用户主页**：资料卡、关注 / 已关注、帖子 / 收藏 / 评论三个列表
* **世界频道**：`/api/world/ALL` + 20 秒轮询、发送消息、头像可点进个人主页
* **WIKI**：原生 Compose 重写（首页 / 官方 / 个人 / 鼠标 / Linux 版）；仅 Live2D 交互模型子页保留“去壳 WebView”（注入样式隐藏网页头部 / 侧边栏 / 页脚，并把 CSS 变量改写为 App 配色）
* **我的 / 设置**：主题（浅色 / 深色 / 跟随系统）、年制（无限年 / 公元年，含示例）、版本 / 服务端 / 客户端标识、**检查更新**、快捷入口
* **支持作者**：我的页常驻赞赏码区块（远端图床图，由 Coil 落盘缓存，不重复下载）
* **应用自更新**：冷启动静默检查（每 24 小时最多一次；也可在「我的 › 关于」手动检查）；下载回退链「直连 GitHub → 公共加速（ghproxy.net / gh-proxy.com / ghfast.top）→ 站内反代」，下载后校验体积 + sha256，再经 FileProvider 调起系统安装器（首次会引导「安装未知应用」授权）
* **彩蛋**：底部第 6 个「彩蛋」标签（对齐网页手机端），每次随机奉上一条 `/Easter-Egg` 彩蛋或「每日一言」
* **隐私政策与服务协议**：我的页二级入口「隐私政策」（v2.1 全文，仅取 Android 可见段）、「注销账号」（彻底删除 / 匿名化保留，密码或邮箱验证码验证 + 输入「注销账号」四字 + 二次确认）
* **首启隐私政策同意门**：首次安装启动（或政策版本升级后）弹出**不可绕过**的同意弹窗，须手动勾选「我已阅读并同意《隐私政策》」后「同意并继续」才可用；「不同意」直接退出应用；同意前**不发起任何网络请求**（冷启动的会话刷新与自动检查更新均延后到同意之后）
* **主题**：4 套色板 + 国庆假期强制叠加（与 Web / Windows 三端同语义）
* **编辑资料**：「我的 › 编辑资料」（资料卡按钮 + 快捷入口双入口）——头像上传（相册选图，≤5MB，随选随传）、昵称 / 性别 / 出生日期（年-月-日三下拉 + 「不展示出生日期」）/ 简介，保存走 `PUT /api/user/info`
* **账号安全**：编辑资料页内「修改密码」（邮箱验证码 + 新密码）、「更换绑定邮箱」（当前邮箱 + 新邮箱双验证码）、「注销账号」入口
* **评论点赞**：帖子详情支持点赞 / 取消点赞评论（用接口返回值就地更新，不重新拉帖以免浏览量虚增）
* **用户主页评论跳转**：评论列表显示「评论于 <帖子标题>」，点击整行进入对应帖子详情
* **评论数显示**：帖子详情与列表优先采用服务端 `comment_count`，字段缺失时回退为已加载评论条数（修复「评论数恒为 0」）
* **正文渲染**：`core/MarkdownBody.kt` 纯 Kotlin 实现 Markdown 子集解析（标题 / 列表 / 引用 / 代码块 / 分隔线 / 粗斜体 / 删除线 / 行内代码 / 链接），无 Android 依赖；单换行即换行（对齐网页端 `breaks:true`）、空行分段，行内文本先做 HTML 转义（HTML 标签以字面文字出现）
* **正文换行修复（V1.0.9）**：段落 / 引用块此前是「先把多行拼成 `<br>`、再整体做 HTML 转义」，结果 `<br>` 被自己的转义逻辑变成字面文字，正文里直接显示「`<br>`」而不是换行（数据库存的其实是普通 `\n`）。现改为**逐行 `inline()` 之后再拼 `<br>`**；并新增 `app/src/test/java/top/crazying/forum/core/MarkdownBodyTest.kt`（6 例）作为回归覆盖，`gradlew testDebugUnitTest` **6/6 通过**。
* **本地缓存「最多 24 小时」（V1.0.10）**：`core/CachePolicy.kt` 新统一策略（`MAX_AGE_MS = 24h`），三处接入：
  * **图片缓存**：`ForumApp` 实现 `SingletonImageLoader.Factory` 自定义 Coil 单例，磁盘缓存按 24 小时时段分目录（`cacheDir/image_cache/<时段>`），启动时整体作废上一时段 —— 任何图片最多被使用 24 小时；
  * **更新包缓存**：`cacheDir/updates/` 启动时清掉 mtime 超过 24 小时的安装包；
  * **用户资料缓存**：`Prefs.saveUserJson()` 同时记写入时间戳，`App.userCacheStale` 暴露过期状态；过期后仍先用旧数据渲染头部，再静默刷新覆盖（失败保留旧数据）。
  * 新增 `app/src/test/java/top/crazying/forum/core/CachePolicyTest.kt`（7 例）。
* **最低版本闸门（V1.0.11）**：与 Web / Windows 三端同源。`Constants` 新增 `CLIENT_PLATFORM = "android"` 与 `CLIENT_HEADERS`（`X-Client-Platform` / `X-Client-Version`），由 `clientHeaderInterceptor()` 挂在 OkHttp 请求链最外层——`Api.request`、头像上传、`fetchText`、`Updater` 下载客户端全自动携带；服务端对低于发布清单 `min_versions.android` 的请求返回 **HTTP 426 + `code=VERSION_TOO_LOW`**，客户端在 `Api.request` 里识别后写入 `App.versionGate`，`ForumRoot` 随即弹出**不可绕过**的「版本过低」弹窗（返回键 / 外部点击均无效，只有「去更新」与「退出应用」两个出口）。新增 `app/src/test/java/top/crazying/forum/core/VersionGateTest.kt`。
* **人机验证（V1.0.12 自研滑块 → V1.0.13 接入 Cloudflare Turnstile）**：与 Web / Windows 三端同源，provider 由服务端 `/api/captcha/challenge` 下发（`turnstile` / `slider` / `enabled=false`）。
  * `core/Captcha.kt`：纯逻辑层——错误码 `CAPTCHA_REQUIRED`、受保护端点表、data URL 解析、拖拽坐标映射（`pieceXFromDrag` / `handleXFromPiece`），以及把业务协程挂起的 `CaptchaPrompt`（`ask()` / `complete()`）与顶层 `askCaptcha()`。
  * **默认 `turnstile`**：`ui/CaptchaDialog.kt` 用 WebView 加载服务端 `/captcha-embed?theme=&lang=&size=flexible`，Cloudflare 官方组件在网页内渲染；token 经 JS bridge（`AndroidCaptcha.onEvent`，`@JavascriptInterface` + `Handler(Looper.getMainLooper()).post` 切回主线程）回传，并以 `WebChromeClient.onReceivedTitle` 解析 `captcha:token:<TOKEN>` 作兜底。Turnstile token **一次性**，拿到即关弹窗，不再走 `/verify` 两步式。
  * **兜底 `slider`**：仍保留自研滑块拼图（`CaptchaHost()` 挂在 `ForumRoot`，由 `CaptchaPrompt.dialogVisible` 驱动——背景图 + 可拖动拼图块 + 滑条手柄，拖拽距离按**实际渲染宽度**等比映射为拼图块 x，故上报的 `captcha_x` 与服务端容差同尺）；服务端未配置 Turnstile 密钥时自动回退到这条路径。
  * **`enabled == false`**：服务端已关闭验证，直接以空 token 放行、不打扰用户。
  * **修复（现象：拖到正确位置后没任何提示就直接重新开始）**：此前失败文案写入 `status` 后立即被 `load()` 重置为「正在加载验证图像…」，错误提示实际存活时长为 0。现拆成 `hint`（中性状态）与 `error`（失败原因）两个独立状态，失败原因作为参数传给 `load(errorText)` 保留显示。
  * 接入点（`captchaToken` 参数为空时不往请求体里加字段，保持老流程不变）：登录 / 注册 / 注销账号验证码 / 注销账号 / 修改密码验证码 / 更换邮箱-当前邮箱验证码 / 更换邮箱-新邮箱验证码，共 7 处；`/api/user/password`、`/api/user/email` 两个终步服务端未设闸门，客户端同样不带。
  * `core/Captcha.kt` 新增纯函数：`providerOf()`（未知 / 空值一律回退 slider）、`embedUrl()`（拼承载页 URL，含 theme / lang / size 归一化）、`eventOf()` / `tokenFromEvent()`（解析承载页回传事件）。
  * `app/src/test/java/top/crazying/forum/core/CaptchaTest.kt` 扩到 24 例（含「弹窗确实接了 Turnstile 桥」「`CaptchaHost` 只声明一次」的源码扫描）。
* **隐私政策 v2.1（V1.0.13）**：新增 Cloudflare Turnstile 第三方披露（`challenges.cloudflare.com` — 人机验证；触达端：三端）与「境外传输提示」（验证请求由设备直连 Cloudflare，可能含 IP 与浏览器环境信息，不含账号信息）；`Constants.PRIVACY_POLICY_VERSION` 由 `2.0` 升至 `2.1`，首启同意门据此重新征得同意。
* **Turnstile 失败自动回退 + 滑块窄屏修复（V1.0.14）**：
  * **自动回退**：Turnstile 组件报错 / 承载页加载失败（`onReceivedError` 主文档）/ 12 秒内页面未加载完成 → 自动改要一帧自研滑块挑战（服务端 `?provider=slider` 强制下发），只回退一次；回退后「刷新」也不再回到 Turnstile。`core/Captcha.kt` 新增纯函数 `challengePath(provider)`，`Api.captchaChallenge(provider)` 支持强制 provider。
  * **修复（现象：图片挤压变形、验证永远失败）**：`ui/CaptchaDialog.kt` 的 `SliderStageView` 原以固定 `320dp` 宽渲染 320px 图片，窄屏被 Compose 压缩后 `ContentScale.FillBounds` 把图拉扁，且滑块行程按**逻辑宽度**计算 → 上报 `captcha_x` 与实际对齐的缺口位置不符。现改用 `BoxWithConstraints` 取**实际可用宽度**等比缩放（背景 / 拼图块 / 行程 / 手感全部同尺），`captcha_x` 仍是服务端图像像素，服务端容差判定不变。
* **验证弹窗可见性修复 + 网页端登录 + 世界频道顺序（V1.0.15）**：
  * **修复（现象：验证组件靠上、被遮挡、点不到）**：此前把承载页 WebView 挂在 `AlertDialog` 的 `text` 槽里——WebView 处于**独立 Dialog 窗口**时，窗口层级与触摸命中区会错位，表现为官方组件看着渲染出来了却点不动。现改为**当前界面内的全屏遮罩层**（`Box` + 居中卡片，附 `BackHandler`），与 App 内已验证可用的 Live2D WebView（`WikiScreen.WikiLive2DBody`）走同一条渲染路径；同时 WebView 高度由 170dp 放宽至 260dp，并在 `setOnTouchListener` 里 `requestDisallowInterceptTouchEvent(true)` 让 WebView 独占手势。
  * **手动退路**：Turnstile 分支新增「改用滑块」按钮（不必再等 12 秒超时），点一下即以 `?provider=slider` 重新要一帧自研滑块挑战。
  * **新增网页端登录**：`ui/screens/WebLoginScreen.kt` 用内置 WebView 打开站点真实登录页 `/auth?mode=login`——官方 Turnstile 在真实网页里渲染，绕开内嵌承载页的一切兼容问题；登录成功后从 `CookieManager` 取出 `token` / `ID` 两个 HttpOnly Cookie，经 `Api.importWebCookies()` 搬进 App 的 OkHttp `PrefsCookieJar`，会话即迁移完成。入口在登录页「使用网页端登录」。因为站点登录走 `fetch()` **不触发页面跳转**，判定成功靠**定时读 Cookie**（1.2 秒一次）+ 顶部「我已完成」手动重试。
  * **修复（现象：世界频道最新消息跑到最上面）**：服务端 `get_world_messages()` 是 `ORDER BY created_at DESC`（最新在前），客户端此前原样渲染。现经 `core/WorldFeed.newestLast()` 转为「早的在上、最新在下」，与聊天窗口一致，并在首次加载与发送成功后自动滚到底部。顺带修正截断口径：原来用 `takeLast(100)`，在倒序列表上取到的是**最旧**的 100 条，现改为 `take(100)`。
  * 新增 `core/WebAuth.kt` / `core/WorldFeed.kt` 两个纯逻辑对象与对应 JVM 单测（`WebAuthTest` 8 例 / `WorldFeedTest` 6 例）。

### 未实现（后续多轮持续补齐）

邮箱验证码注册、会馆、举报、收藏独立页、Live2D 桌宠、鼠标指针、深链、世界频道 WebSocket（当前为轮询）、正文内联图片渲染、富文本编辑器。

---

## 六、后续计划

1. **补齐上述未实现功能**，优先顺序：邮箱验证码注册 → 删除 / 举报 → 收藏独立页。
2. **世界频道升级为 WebSocket**（当前 20 秒轮询，服务端对发送有 2 秒 / 人 限流）。
3. **正文内联图片**：`HtmlBody` 目前会剥离 `<img>`，可换成 Coil + `ImageGetter`。
4. **AGP 9.x 升级**：用 Android Studio 的 AGP Upgrade Assistant 迁移（删除 `org.jetbrains.kotlin.android`，改用内置 Kotlin DSL），并同步升级 Gradle。
5. ~~**签名与发布**~~：已完成 —— 仓库根 `keystore.properties` + `app/build.gradle.kts` 的 `signingConfigs`，`assembleRelease` 直接产出已签名 release APK（凭据已 git-ignore，不入库）。

---

## 七、已知限制与注意事项

* **WIKI 已全面原生化**：首页 / 官方 / 个人 / 鼠标 / Linux 版均为 Compose；仅 **Live2D 交互模型** 子页保留 WebView（网页 canvas + Live2D 运行时，无法用 Compose 复刻），并在 `onPageFinished` 注入样式隐藏网页外壳、改写 CSS 变量为当前 App 配色。
* **网页端登录的会话来源**：走内置 WebView 登录后，App 的登录态就是网页下发的 Cookie（`token` / `ID`，有效期 7 天）。若在网页侧退出登录，App 侧会因 Cookie 失效而被服务端 401 → 自动清理本地会话。
* **WebView 不要放进 Dialog**：Android 上 `AndroidView` 承载的 WebView 位于独立 Dialog 窗口时，层级与触摸命中区会错位（要么看不见，要么看得见点不到）。本工程的人机验证与网页登录都因此改为**页面内组合**渲染，后续新增 WebView 界面请沿用同一做法。
* **正文内联图片不显示**：`HtmlBody` 主动剥离 `<img>` / `<script>`，只保留文字、段落、粗体、链接、代码块等常用标签。
* **`auto` 主题语义**：Android 取「跟随系统深色模式」，与 Web / Windows 的「小时切换」不同（有意为之）。
* **Coil 3 的网络加载器**：依赖 `coil-network-okhttp` 的 ServiceLoader 自动注册；若自定义 `ImageLoader` 需手动装配 `OkHttpNetworkFetcherFactory`。
* **头像无占位图**：URL 为空时渲染「猫」字占位，尚未接入错误 / 占位 painter。
* **服务端不可达时**：`Api` 对 GET 请求重试 1 次（写操作绝不重试，避免重复发帖 / 评论）；返回 401 会静默清理本地会话。
* **`local.properties` 严禁入库**（已在 `.gitignore` 中）；`gradle-wrapper.jar` 相反 **必须入库**。
* **签名材料**（`*.jks` / `*.keystore` / `keystore.properties`）同样已 git-ignore。
* **自更新的额外出网域名**：应用主体只连 `https://www.yjlt.top`，但自更新下载会额外访问 GitHub 直链与三个公共加速镜像；彩蛋页的「每日一言」还会访问第三方 `dlystc.unknownmp.top`。Android 端**有意不做** Windows 那样的 DoH / DNS 接管（OkHttp 走系统解析，改造收益不值当）。
* **自动更新的触发时机**：仅冷启动检查一次，且距上次检查不足 24 小时会跳过；用户点过「以后再说」的版本不再自动弹窗（手动「检查更新」仍会显示）。发现新版本后仍需用户在对话框中确认，不会静默安装（Android 也不允许）。

---

## 八、构建验证记录

本工程已在本机完成**真实编译验证**（非“写而未编”）：

| 项 | 结果 |
| --- | --- |
| JDK | Microsoft OpenJDK **17.0.20.1**（JAVA_HOME / Gradle Daemon JVM 均为它） |
| Android SDK | `cmdline-tools 16111833`、`platform-tools r37.0.1`、`platforms;android-36`、`build-tools;36.0.0` |
| Gradle | 8.14.5（Wrapper 自带的发行包） |
| 命令 | `.\gradlew.bat testDebugUnitTest assembleRelease --console=plain` |
| 结果 | **BUILD SUCCESSFUL**（63 例全部通过：CaptchaTest 26 / VersionGateTest 10 / CachePolicyTest 7 / MarkdownBodyTest 6 / WebAuthTest 8 / WorldFeedTest 6） |
| Release 产物（V1.0.15） | `app\build\outputs\apk\release\app-release.apk`，**8 152 504 字节**，sha256 `1ca33a725c381683843956797caa206a5d7ff0d20efc7900cb110e9b78d36960`，APK 签名证书 SHA-256 `bab9ac497b3b5b4f8fe3e36fbb9fec111c08831dc6e9100889a439f019aa4668` |
| 历史 Release 产物（V1.0.13） | `app\build\outputs\apk\release\app-release.apk`，**8 152 504 字节**，sha256 `f9c201a574cfba4006b7b0442b41de4258781207ac884c97226d87e25dd10385` |

编译过程中定位并修正的 3 类真实问题（供后续参考）：

1. **依赖代际不匹配**：直接取“最新版”会导致 `checkDebugAarMetadata` 失败（新版 AAR 要求 AGP ≥ 9.1.0 / compileSdk ≥ 37）→ 已改为与 AGP 8.13.2 同代的稳定组合。
2. **尾随 lambda 绑定到 `Modifier`**：`Pill(text, active, onClick, modifier)` 的参数顺序使 `Pill("x", active = true) { … }` 的 lambda 绑到 `modifier` → 已把 `onClick` 调到最后一个参数。
3. **可空接收者**：`ApiResult.rows()` 里 `val arr: JSONArray? = … ?: return` 显式声明为可空，导致后续调用报错 → 已去掉显式可空声明。
