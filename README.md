# 妖精论坛 · Android 客户端

原生 **Kotlin + Jetpack Compose** 重写版，与 Web 端（`forum`）和 Windows 端（`forum-windows`）共用同一套服务端与主题色板。

| 项 | 值 |
| --- | --- |
| 当前版本 | **V1.1.0**（`versionCode = 10100`） |
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
| WebView | **仅一处**：WIKI › Live2D 子页 | 其余界面（含 WIKI 其他子页、登录/注册、人机验证）均为 Compose 原生绘制；网页端登录已移除 |
| 应用更新 | 自写 `Updater`（`core/Updater.kt`） | GitHub Releases 优先 → 服务端清单兜底 → 三级回退下载 → sha256 校验 → 文件提供器调起系统安装器 |

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

`无限年 = 公元年 − 1603`（无限元年 = 公元 1604 年，无限年 **1 起算**）；公元年 < 1604 时显示「无限前 N 年」（无限前 N 年 = 公元 (1604 − N) 年，不存在无限 0 年）。影响帖子 / 评论 / 注册时间的年份显示。

### 图标

启动图标直接使用**原项目图标**（`forum/static/img/favicon.png`，1080×1080，与网站头部 / `apple-touch-icon`、Windows 端 `icon.ico` 同源），
由 `tools/gen-android-icons.ps1` 生成 `mipmap-*` 五档密度的方形 / 圆形图标，以及 API 26+ 自适应图标的前景层（背景层 `#FFFFFF`）。

### 接口

全部走 `https://www.yjlt.top` 的 **ouo canonical `/ov2/api`**，不再使用旧 APP 兼容层 `/api/*`：

```
认证   POST /ov2/api/auth/login | /auth/logout | /auth/register
       POST /ov2/api/auth/register/code
       GET  /ov2/api/users/me          PATCH /ov2/api/users/me
       POST /ov2/api/users/me/avatar
       POST /ov2/api/users/me/email-change/{code,verify-old,new-code,confirm}
       POST /ov2/api/users/me/delete
帖子   GET  /ov2/api/posts | /posts/random | /posts/<id>
       POST /ov2/api/posts | /posts/<id>/like | /favorite | /delete
评论   GET  /ov2/api/posts/<id>/comments   POST /ov2/api/posts/<id>/comments
       DELETE /ov2/api/comments/<id>        POST /ov2/api/comments/<id>/like
用户   GET  /ov2/api/users/<id> | /posts | /favorites | /comments | /following | /followers
       POST /ov2/api/users/<id>/follow
搜索   GET  /ov2/api/search
世界   GET  /ov2/api/world/messages      POST /ov2/api/world/messages
媒体   POST /ov2/api/media/images        GET /ov2/api/media/<id>
引用   GET  /ov2/api/embeds
彩蛋   GET  /ov2/api/easter-egg
更新   GET  /ov2/api/downloads/check?platform=android&version=<版本>
       GET  /ov2/api/downloads/mirror/android/<文件名>   （站内反代 GitHub 直链）
验证   GET  /ov2/api/captcha/config | /captcha/challenge
       POST /ov2/api/captcha/verify
```

CSRF：ouo 要求非 GET 请求带同源 `Origin`/`Referer`；`Api` 的同源拦截器统一补上（只对 `BASE_URL` 同源生效）。

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
            │   ├── Api.kt                  ApiResult + Api（全部 /ov2/api 接口 + ALTCHA 会话）
            │   ├── Altcha.kt               ALTCHA v2：字节精确 Mac PBKDF2 求解 / payload / prefix
            │   ├── AltchaUi.kt             验证弹窗状态（求解 / 失败重试）
            │   ├── richtext/RichDocument.kt 富文本模型 + HTML/Markdown 互转
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
                ├── richtext/               富文本渲染 / 跨段选区编辑器 / 全屏宿主 / 引用卡片
                └── screens/                15 个页面（发帖/评论共用全屏编辑器）
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
.\gradlew.bat assembleRelease      # 未开启混淆；有签名凭据（环境变量或 keystore.properties）时自动签名
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

### 4. 版本号规则（唯一真相源）

版本号只维护 **`app/build.gradle.kts` 里的 `val appVersionName = "1.1.0"` 一处**，其余全部由它派生：

* `versionCode = major × 10000 + minor × 100 + patch`：`1.1.0 → 10100`、`1.0.18 → 10018`；预发布后缀只保留在 `versionName` 里，`versionCode` 只取数字基段（`1.2.0-beta1 → 10200`）。
* Gradle 生成 `BuildConfig.APP_VERSION`，`core/Constants.kt` 的 `Constants.APP_VERSION` 直接读它，工程里不再有第二份版本字面量。
* 发布 tag 必须是 `Android-V<versionName>`（如 `Android-V1.1.0`）；Release 工作流会传 `-PexpectedVersion=<tag 版本>` 校验源码版本，不一致直接构建失败（例如 tag 为 `Android-V9.9.9` 时会报「tag 版本 9.9.9 与 versionName 1.1.0 不一致」）。
* **发布 tag 只接受三段纯数字**：`Android-V1.2.0-beta1` 这类带后缀的 tag 会被 Release 工作流直接拒绝（Gradle 允许写后缀仅便于本地实验，CI 不发布预发布版）。

### 5. 本地签名构建（可选）

签名材料 **不在仓库内**，放在仓库外的 `~/.android/keys/`（keystore `forum-release.jks`，alias `forum`，证书 SHA-256 `bab9ac497b3b5b4f8fe3e36fbb9fec111c08831dc6e9100889a439f019aa4668`）。Linux / bash 下完整命令：

```bash
cd ~/yjlt/yj-forum-android
KEYSTORE_DIR="$HOME/.android/keys"
# 需要 JDK 17+；本机为 JetBrains Runtime 21，SDK 在 ~/Android/Sdk
export JAVA_HOME=/home/yoyo/.jdks/jbr-21.0.11
export PATH="$JAVA_HOME/bin:$PATH"   # apksigner 需要 PATH 上有 java
export ANDROID_HOME="$HOME/Android/Sdk"

# 四项凭据齐备且 keystore 存在才会签名；缺任意一项则产出未签名包
export ANDROID_KEYSTORE_FILE="$KEYSTORE_DIR/forum-release.jks"
export ANDROID_KEYSTORE_PASSWORD="$(sed -n 's/^storePassword=//p' "$KEYSTORE_DIR/keystore.properties" | head -n1)"
export ANDROID_KEY_ALIAS="$(sed -n 's/^keyAlias=//p' "$KEYSTORE_DIR/keystore.properties" | head -n1)"
export ANDROID_KEY_PASSWORD="$(sed -n 's/^keyPassword=//p' "$KEYSTORE_DIR/keystore.properties" | head -n1)"

# 本机 gradlew 是无执行位的 100644：用 bash 调用，或本地 chmod +x（不要把文件模式变更提交）
bash ./gradlew assembleRelease -PexpectedVersion=1.1.0

# 产物与验签
ls -l app/build/outputs/apk/release/app-release.apk
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --print-certs \
  app/build/outputs/apk/release/app-release.apk | grep 'certificate SHA-256'
```

* 只有 `ANDROID_KEYSTORE_FILE` / `ANDROID_KEYSTORE_PASSWORD` / `ANDROID_KEY_ALIAS` / `ANDROID_KEY_PASSWORD` **全部齐备**且 keystore 文件存在时才会签名；否则 release 照常构建，但产出的是 **未签名** `app-release.apk`。（旧的仓库根 `keystore.properties` 仍作为兜底读取，但仓库里已没有该文件。）
* `-PexpectedVersion` 是可选的本地校验，不传则不校验；正式发版由 CI 传入 tag 版本。

### 6. GitHub Actions：CI 与 tag 发版

| 工作流 | 触发条件 | 做什么 |
| --- | --- | --- |
| `.github/workflows/android-ci.yml` | push 到 `Android` 分支 / PR 目标为 `Android` / 手动 `workflow_dispatch` | `testDebugUnitTest` + `assembleDebug`，上传 `android-debug-apk` 制品（保留 7 天） |
| `.github/workflows/android-release.yml` | push tag `Android-V*` | `build` 作业：校验 tag 指向的提交在 `Android` 分支 → 还原 keystore → `assembleRelease -PexpectedVersion=<tag 版本>` → `apksigner` 验签（断言证书 SHA-256）→ 重命名 `forum-android-<版本>.apk` → 生成 notes → 上传制品；`publish` 作业（需 `contents: write`）：发 GitHub Release |

> ⚠️ 两个工作流都保留 `workflow_dispatch`，但 GitHub 规定**手动触发要求工作流已存在于默认分支**；本仓库默认分支是 `main`、工作流只随 `Android` 分支提交，所以当前实际以 **tag 发版**为准（CI 由分支 push / PR 自动触发）。

仓库级 Secrets（Settings → Secrets and variables → Actions，共 4 条）：

| Secret | 用途 |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | `forum-release.jks` 的 base64（工作流还原到 runner 临时目录） |
| `ANDROID_KEYSTORE_PASSWORD` | keystore 密码 |
| `ANDROID_KEY_ALIAS` | 密钥别名（`forum`） |
| `ANDROID_KEY_PASSWORD` | 密钥密码 |

**发布流程**：

1. 修改 `app/build.gradle.kts` 的 `appVersionName`（见上一节）。
2. 提交并推送 `Android` 分支。
3. 打 tag 并推送：`git tag Android-V1.1.0 && git push origin Android-V1.1.0`（tag 必须与 `appVersionName` 完全一致）。
4. 等 Actions 的 **Android Release** 跑完。
5. 校验 Release 资产：`forum-android-1.1.0.apk`，以及 release notes 里的字节数 / SHA-256 / 证书指纹（`bab9ac…aa4668`）。

**安全约束**：

* fork 提交的 PR **不会**注入仓库 Secrets（CI 本身也不需要），无法借 PR 获取签名凭据。
* 只有 **tag push** 会发布 Release；且 tag 必须指向 `Android` 分支上的提交（工作流会做祖先校验），否则拒绝发布。
* 构建作业只有 `contents: read`，发布作业才拿 `contents: write`；checkout 不持久化凭据（`persist-credentials: false`）。
* 密钥只能放在 GitHub Secrets 或本机仓库外，**不得**写进仓库、README、构建日志或提交历史。

---

## 五、本轮已实现 / 未实现

### 已实现（V1.1.0 概览）

* **账号**：登录（用户名或邮箱）、注册（用户名 + 邮箱 + **邮箱验证码**）、退出登录、本地会话恢复与失效清理；注册/登录自动完成 ALTCHA
* **首页**：最新发布 / 随机推荐 两个信息流（最新发布分页加载；随机推荐单页），ov2 不支持 comprehensive 排序已移除该 Tab；「我的收藏」流已从首页移除，可在「我的 → 主页 → 收藏」查看
* **论坛**：全部 + 5 个分类（综合 / 闲聊 / 求助 / 分享 / 创作），分页加载
* **帖子详情**：作者信息、**富文本正文**（按 `content_format` 分流：html 富文本 / 历史 markdown）、内联图片、引用卡片、点赞 / 收藏（就地刷新，不重复计入浏览量）、楼中楼评论（两层：根 + 回复，深层压平并以「回复 @昵称」标注）、发评论 / 回复、删除自己的帖子 / 评论（二次确认）
* **发帖**：分类选择、标题（≤ 100 字）、**自建 WYSIWYG 富文本编辑器**（跨段选区、粗/斜/下划线/删除线/行内代码/链接、H1~H3、有序/无序列表、引用、代码块、分割线、图片块、撤销重做）；提交时转成服务端白名单 HTML
* **搜索**：帖子 + 用户，支持「全部 / 帖子 / 用户」筛选
* **用户主页**：资料卡、关注 / 已关注、帖子 / 收藏 / 评论三个列表
* **世界频道**：`GET /ov2/api/world/messages` + 20 秒轮询、富文本气泡（历史消息可能含图片）、**底部内联纯文本输入框直接发送**（不支持富文本与图片）、头像可点进个人主页
* **WIKI**：原生 Compose 重写（首页 / 官方 / 个人 / 鼠标 / Linux 版）；仅 Live2D 交互模型子页保留“去壳 WebView”（注入样式隐藏网页头部 / 侧边栏 / 页脚，并把 CSS 变量改写为 App 配色）
* **我的 / 设置**：主题（浅色 / 深色 / 跟随系统）、年制（无限年 / 公元年，含示例）、版本 / 服务端 / 客户端标识、**检查更新**、快捷入口
* **启动公告**：每次冷启动弹一次，说明 ov2 APP 开发计划（本版本仍会收到必要的升级推送）
* **支持作者**：我的页常驻赞赏码区块（远端图床图，由 Coil 落盘缓存，不重复下载）
* **应用自更新**：冷启动静默检查（每 24 小时最多一次；也可在「我的 › 关于」手动检查）；下载回退链「直连 GitHub → 公共加速（ghproxy.net / gh-proxy.com / ghfast.top）→ 站内反代」，下载后校验体积 + sha256，再经 FileProvider 调起系统安装器（首次会引导「安装未知应用」授权）
* **彩蛋**：底部第 6 个「彩蛋」标签（对齐网页手机端），每次随机奉上一条 `/Easter-Egg` 彩蛋或「每日一言」
* **隐私政策与服务协议**：我的页二级入口「隐私政策」（v2.2 全文，仅取 Android 可见段）、「注销账号」（彻底删除 / 匿名化保留，**密码 + 输入当前用户名** + 二次确认）
* **首启隐私政策同意门**：首次安装启动（或政策版本升级后）弹出**不可绕过**的同意弹窗，须手动勾选「我已阅读并同意《隐私政策》」后「同意并继续」才可用；「不同意」直接退出应用；同意前**不发起任何网络请求**（冷启动的会话刷新与自动检查更新均延后到同意之后）
* **主题**：4 套色板 + 国庆假期强制叠加（与 Web / Windows 三端同语义）
* **编辑资料**：「我的 › 编辑资料」（资料卡按钮 + 快捷入口双入口）——头像上传（相册选图，≤5MB，随选随传）、昵称 / 性别 / 出生日期（年-月-日三下拉 + 「不展示出生日期」）/ 简介，保存走 `PATCH /ov2/api/users/me`
* **账号安全**：编辑资料页内「修改密码」（**当前密码 + 新密码**）、「更换绑定邮箱」（四步：发旧码 → 验证旧码 → 发新码 → 确认）、「注销账号」入口
* **评论点赞**：帖子详情支持点赞 / 取消点赞评论（用接口返回值就地更新，不重新拉帖以免浏览量虚增）
* **用户主页评论跳转**：评论列表显示「评论于 <帖子标题>」，点击整行进入对应帖子详情
* **评论数显示**：帖子详情与列表优先采用服务端 `comment_count`，字段缺失时回退为已加载评论条数（修复「评论数恒为 0」）
* **正文渲染**：`core/richtext/RichDocument.kt` 自建富文本模型 + HTML 解析/序列化（段落、标题、列表、引用、代码块、图片、分割线、引用卡片、行内样式）；`ui/richtext/RichTextView.kt` 统一渲染正文/评论/世界频道；历史 markdown 经 `MarkdownBody.toHtml()` 转入同一模型
* **正文换行修复（V1.0.9）**：段落 / 引用块此前是「先把多行拼成 `<br>`、再整体做 HTML 转义」，结果 `<br>` 被自己的转义逻辑变成字面文字，正文里直接显示「`<br>`」而不是换行（数据库存的其实是普通 `\n`）。现改为**逐行 `inline()` 之后再拼 `<br>`**；并新增 `app/src/test/java/top/crazying/forum/core/MarkdownBodyTest.kt`（6 例）作为回归覆盖，`gradlew testDebugUnitTest` **6/6 通过**。
* **本地缓存「最多 24 小时」（V1.0.10）**：`core/CachePolicy.kt` 新统一策略（`MAX_AGE_MS = 24h`），三处接入：
  * **图片缓存**：`ForumApp` 实现 `SingletonImageLoader.Factory` 自定义 Coil 单例，磁盘缓存按 24 小时时段分目录（`cacheDir/image_cache/<时段>`），启动时整体作废上一时段 —— 任何图片最多被使用 24 小时；
  * **更新包缓存**：`cacheDir/updates/` 启动时清掉 mtime 超过 24 小时的安装包；
  * **用户资料缓存**：`Prefs.saveUserJson()` 同时记写入时间戳，`App.userCacheStale` 暴露过期状态；过期后仍先用旧数据渲染头部，再静默刷新覆盖（失败保留旧数据）。
  * 新增 `app/src/test/java/top/crazying/forum/core/CachePolicyTest.kt`（7 例）。
* **最低版本闸门（V1.0.11）**：与 Web / Windows 三端同源。`Constants` 新增 `CLIENT_PLATFORM = "android"` 与 `CLIENT_HEADERS`（`X-Client-Platform` / `X-Client-Version`），由 `clientHeaderInterceptor()` 挂在 OkHttp 请求链最外层——`Api.request`、头像上传、`fetchText`、`Updater` 下载客户端全自动携带；服务端对低于发布清单 `min_versions.android` 的请求返回 **HTTP 426 + `code=VERSION_TOO_LOW`**，客户端在 `Api.request` 里识别后写入 `App.versionGate`，`ForumRoot` 随即弹出**不可绕过**的「版本过低」弹窗（返回键 / 外部点击均无效，只有「去更新」与「退出应用」两个出口）。新增 `app/src/test/java/top/crazying/forum/core/VersionGateTest.kt`。
* **全量迁移 `/ov2/api`（V1.1.0）**：`core/Api.kt` 不再保留任何 legacy `/api/*` 路径；登录/注册/改密/换绑/注销/帖子/评论/用户/搜索/世界/媒体/引用卡片/更新/彩蛋全部切换；同源 `Origin`/`Referer` 拦截器用于通过 ouo CSRF。
* **ALTCHA v2（V1.1.0）**：`core/Altcha.kt` 纯 Kotlin 实现 PBKDF2-HMAC-SHA256 求解——**字节精确**的 `Mac` + `SecretKeySpec(passwordBytes, "HmacSHA256")`（不用 SecretKeyFactory/PBEKeySpec：后者会把 nonce 随机字节按 UTF-8 重编码）；worker 内复用 Mac 与缓冲区、≤4 worker、90s 超时、OOM 减半 worker 重试、取消/异常兜底。`Api` 自动拉 challenge → 求解 → `/captcha/verify` 换 5 分钟 `grant` 并缓存复用；失败 `CAPTCHA_REQUIRED` 自动重解重试一次；`ui/AltchaDialog.kt` 为极简等待卡片（不确定转圈 + 取消验证），失败时同一卡片内切换「具体原因 + 重试 / 取消」。
* **自建富文本（V1.1.0）**：`core/richtext/RichDocument.kt`（模型 + HTML/Markdown 互转）+ `ui/richtext/RichTextView.kt`（正文/评论/世界渲染、图片、引用卡片）+ `RichTextEditor.kt`（跨段选区、块格式、图片、撤销重做）+ `RichTextEditorScreen.kt`（发帖/评论共用全屏宿主）。图片上传走 `POST /ov2/api/media/images`。
* **移除网页登录（V1.1.0）**：删除 `WebLoginScreen`、`WebAuth`、`importWebCookies`、`PrefsCookieJar.put` 与登录页入口；App 不再用 WebView 承载登录或人机验证。
* **世界频道顺序**：`WorldFeed.newestLast()` 保持「早的在上、最新在下」，发送后自动滚到底部；列表读取改为 ov2 的 `{items,...}`。
* **列表页返回保留浏览位置（V1.0.16）**：
  * **修复（现象：从帖子详情退出后，列表跳回最顶端）**：本工程有意不用 `navigation-compose`，根节点用 `when (nav.current)` 只渲染当前页 —— 页面一旦被压栈（进入帖子详情）就离开组合，页内 `remember` 的列表数据与 `LazyListState` 一并被丢弃，返回时列表被清空重载、滚动位置归零。现新增 `ui/screens/FeedState.kt`：`FeedState` / `UserFeedState` / `SearchState` 分别承载首页 / 论坛 / 搜索 / 用户主页的已加载内容、分页游标与 `LazyListState`，由 `ForumRoot` 用 `remember { FeedStateStore() }` 持有（位于 `when` 之外，随根节点存活）；返回列表页时 `store.feed(...)` 仍返回同一实例，列表内容与滚动位置都还在。
  * 配合纯函数 `needReload(loadedKey, currentKey)`：只在内容标识（信息流 / 分类 / 搜索词 / 用户 tab）变化时才重新加载，从帖子详情返回不再触发重载。
  * `FeedParts.PostFeedList` 新增 `state: LazyListState` 参数（默认 `rememberLazyListState()`）；首页 / 论坛把保留的滚动状态传进去，搜索页与用户主页的 `LazyColumn` 同样接入。
  * 新增 `FeedStateTest`（10 例）覆盖 `needReload` 判定与 `FeedStateStore` 的「同 key 同实例」语义。
* **全量迁移 ov2 + ALTCHA + 自建富文本（V1.1.0）**：
  * 所有接口切换到 `/ov2/api`，不再使用 legacy 兼容层；同源 `Origin`/`Referer` 过 CSRF。
  * ALTCHA v2 纯 Kotlin 求解（字节精确 Mac、≤4 worker、90s 超时、失败重试）+ grant 缓存 + 极简等待/失败弹窗；本地端到端测试验证 challenge → solve → verify → grant。
  * 自建富文本模型/解析/序列化/跨段选区编辑器/图片上传/引用卡片；发帖、评论共用编辑器（世界频道已改为内联纯文本输入）。
  * 账号流程按 ov2 重做：邮箱验证码注册、当前密码改密、四步换绑、密码+用户名注销；移除网页登录与旧滑块/Turnstile。
  * 版本号 versionCode 20 / versionName 1.1.0；隐私政策 2.2。

* **年制换算接受公元前（V1.0.18）**：
  * 公元年输入框放开了负数 —— 输入 `-1` 即「公元前 1 年」，输出「公元前 1 年 = 无限前 1604 年」；与 Web 端口径一致（`ceNum < 0 ? ceNum + 1 : ceNum`）。
  * `core/TimeFmt.kt` 新增 `ceInputToAstronomical()` / `ceInputToNewEra()`：把「公元前 M 年 = 天文纪年 `1 − M`」的归一收敛到核心，避免直接拿负数进公式差一年；输入 0 仍按「公元纪年无 0 年」拒绝。
  * `TimeFmtTest` 新增 3 例（公元前换算 / 0 年拒绝 / 正数不变）。
  * 版本号 versionCode 19 / versionName 1.0.18。

* **年制换算与「无限历」结构化重构（V1.0.17）**：
  * **修复（现象：公元 1603 年显示成「无限 0 年」）**：无限历改为 1 起算 —— 无限元年 = 公元 1604 年（`wuxianYear(ce) = ce - 1603`）；公元 1604 年以前显示「无限前 N 年」（无限前 1 年 = 公元 1603 年），不存在无限 0 年。与 Web / Windows 三端口径统一。
  * **重构**：`core/TimeFmt.kt` 新增顶层 `data class NewEraDate(yearNum, isBefore)` 与 `gregorianToNewEra()` / `newEraToGregorian()` / `ceText()`，把「公元年 ⇄ 无限年」双向换算收敛到一个结构化核心（`newEraToGregorian` 对 0 与负数直接拒绝）；`wuxianYear` / `wuxianToCe` / `yearText` 改为委托核心，对外文案仍为「无限 N 年 / 无限前 N 年」。
  * **新增入口**：`ui/screens/YearConvertScreen.kt` 年制换算页（我的 → 快捷入口 → 年制换算），无限年 ⇄ 公元年实时双向换算，对 0 年与负数给出明确提示。
  * `TimeFmtTest` 补充结构化换算 / 往返一致 / 非法输入共 6 例。
  * 版本号 versionCode 18 / versionName 1.0.17。

### 未实现（后续多轮持续补齐）

会馆、举报、收藏独立页、Live2D 桌宠、鼠标指针、深链、世界频道 WebSocket（当前为轮询）、忘记密码/重置密码页、消息中心、嵌套列表、表格/分栏、草稿箱。

---

## 六、后续计划

1. **补齐上述未实现功能**，优先顺序：会馆 → 举报 → 收藏独立页。
2. **世界频道升级为 WebSocket**（当前 20 秒轮询，服务端对发送有 2 秒 / 人 限流）。
3. **编辑器增强**：嵌套列表、表格、跨图片选区、草稿自动保存。
4. **AGP 9.x 升级**：用 Android Studio 的 AGP Upgrade Assistant 迁移（删除 `org.jetbrains.kotlin.android`，改用内置 Kotlin DSL），并同步升级 Gradle。
5. **发布**：已交给 GitHub Actions——推送 `Android-V*` tag 自动签名并发布 Release；本机签名需显式注入 `ANDROID_KEY*` 环境变量。

---

## 七、已知限制与注意事项

* **WIKI 已全面原生化**：首页 / 官方 / 个人 / 鼠标 / Linux 版均为 Compose；仅 **Live2D 交互模型** 子页保留 WebView（网页 canvas + Live2D 运行时，无法用 Compose 复刻），并在 `onPageFinished` 注入样式隐藏网页外壳、改写 CSS 变量为当前 App 配色。
* **WebView 仅 Live2D**：网页登录与 Turnstile/滑块验证已整体移除；新增 WebView 界面仍应避免放进 Dialog（独立窗口下层级/命中区会错位）。
* **富文本编辑器限制**：列表不嵌套；图片/分割线是原子块，选区不能跨过；粘贴一律按纯文本拆段；不支持表格/分栏。
* **世界频道发送限制**：仅支持纯文本（发送前转义特殊字符、换行转 `<br>` 后按 `content_html` 提交）；历史消息仍按富文本渲染，但发送端不再提供图片与格式。
* **ALTCHA 求解耗时**：服务端默认 cost=5000，手机端可能需要数秒；求解用字节精确的 `Mac`（≤4 worker、90s 超时、OOM 减半重试），等待弹窗只显示不确定转圈与「取消验证」，失败可在同一卡片重试/取消；解出的 `grant` 缓存 5 分钟复用。客户端 `cost` 上限为 20000，服务端 `ALTCHA_COST` 若调高必须同步客户端，否则会报「安全验证数据异常」。
* **调试基址**：debug 构建可用 `-PapiBaseUrl=http://10.0.2.2:8090` 指向本地 ouo；release 始终使用 `https://www.yjlt.top`。
* **`auto` 主题语义**：Android 取「跟随系统深色模式」，与 Web / Windows 的「小时切换」不同（有意为之）。
* **Coil 3 的网络加载器**：依赖 `coil-network-okhttp` 的 ServiceLoader 自动注册；若自定义 `ImageLoader` 需手动装配 `OkHttpNetworkFetcherFactory`。
* **头像无占位图**：URL 为空时渲染「猫」字占位，尚未接入错误 / 占位 painter。
* **服务端不可达时**：`Api` 对 GET 请求重试 1 次（写操作绝不重试，避免重复发帖 / 评论）；返回 401 会静默清理本地会话。
* **`local.properties` 严禁入库**（已在 `.gitignore` 中）；`gradle-wrapper.jar` 相反 **必须入库**。
* **签名材料**（`*.jks` / `*.keystore` / `keystore.properties`）同样已 git-ignore；实际材料在仓库外 `~/.android/keys/`（仓库内不存在）。本机不注入 `ANDROID_KEY*` 环境变量时只产出未签名包，正式包由 CI 用 GitHub Secrets 签名。
* **更新源**：APP 优先直连 GitHub Releases（`yoyo-ouo/yj-forum-ouo`，筛 `Android-V*` 且带 `.apk`），失败才回退服务端 `/ov2/api/downloads/check`；下载链的「站内反代」回退要求服务端发布源也指向同一仓库。
* **自更新的额外出网域名**：应用主体只连 `https://www.yjlt.top`，但自更新下载会额外访问 GitHub 直链与三个公共加速镜像；彩蛋页的「每日一言」还会访问第三方 `dlystc.unknownmp.top`。Android 端**有意不做** Windows 那样的 DoH / DNS 接管（OkHttp 走系统解析，改造收益不值当）。
* **自动更新的触发时机**：仅冷启动检查一次，且距上次检查不足 24 小时会跳过；用户点过「以后再说」的版本不再自动弹窗（手动「检查更新」仍会显示）。发现新版本后仍需用户在对话框中确认，不会静默安装（Android 也不允许）。

---

## 八、构建验证记录

本工程已在本机完成**真实编译验证**（非“写而未编”）：

| 项 | 结果 |
| --- | --- |
| JDK | 源码 target 17；本机用 JetBrains Runtime **21.0.11** 跑 Gradle（`JAVA_HOME=/home/yoyo/.jdks/jbr-21.0.11`） |
| Android SDK | `platform-tools`、`platforms;android-36`、`build-tools;36.0.0` |
| Gradle | 8.14.5（Wrapper 自带的发行包） |
| 命令 | `JAVA_HOME=/home/yoyo/.jdks/jbr-21.0.11 bash ./gradlew testDebugUnitTest assembleDebug` |
| 结果 | **BUILD SUCCESSFUL**（**129 tests，128 通过 + 1 跳过**：AltchaTest 21 / AltchaUiTest 6 / AltchaLiveTest（env 缺省跳过）1 / RichDocumentTest 16 / TextLimitTest 5 / ModelsTest 5 / TimeFmtTest 18 / UpdateParserTest 19 / VersionGateTest 10 / FeedStateTest 9 / CachePolicyTest 7 / MarkdownBodyTest 6 / WorldFeedTest 6） |
| Debug 产物（V1.1.0） | `app/build/outputs/apk/debug/app-debug.apk`，**12 351 071 字节**，sha256 `b06790802636f2da90e60069e713bd9743de3046081000b647634df25c8c9253`；`BuildConfig.API_BASE_URL=https://www.yjlt.top` 已核对；release 见下一行（本机以环境变量注入签名凭据构建） |
| Release 产物（V1.1.0 本地签名验证） | `app/build/outputs/apk/release/app-release.apk`，**8 234 428 字节**，sha256 `bcf69a164818ad759888b557e6b533abb141a5e461b74f217426d88828dab208`，APK 签名证书 SHA-256 `bab9ac497b3b5b4f8fe3e36fbb9fec111c08831dc6e9100889a439f019aa4668`（与旧版一致）；构建命令含 `-PexpectedVersion=1.1.0` |
| Release 产物（V1.0.18） | `app\build\outputs\apk\release\app-release.apk`，**8 168 888 字节**，sha256 `f410be372e0b5c0327d6d64a6ca8e8fc4efc5f2ee56fd56645f877616875f276`，APK 签名证书 SHA-256 `bab9ac497b3b5b4f8fe3e36fbb9fec111c08831dc6e9100889a439f019aa4668`；发布包副本 `release\forum-android-1.0.18.apk` |
| 历史 Release 产物（V1.0.17） | `app\build\outputs\apk\release\app-release.apk`，**8 168 888 字节**，sha256 `0d36a0626ed8e870eed4a1497c7178ae8e76fea9178cdcf5288b68b4ad399287` |
| 历史 Release 产物（V1.0.16） | `app\build\outputs\apk\release\app-release.apk`，**8 152 504 字节**，sha256 `1bedfc7f3e29a616d217762a9907f846f2d17cf1eb843cf90fd041010b2cdd61` |
| 历史 Release 产物（V1.0.15） | `app\build\outputs\apk\release\app-release.apk`，**8 152 504 字节**，sha256 `1ca33a725c381683843956797caa206a5d7ff0d20efc7900cb110e9b78d36960` |
| 历史 Release 产物（V1.0.13） | `app\build\outputs\apk\release\app-release.apk`，**8 152 504 字节**，sha256 `f9c201a574cfba4006b7b0442b41de4258781207ac884c97226d87e25dd10385` |

编译过程中定位并修正的 3 类真实问题（供后续参考）：

1. **依赖代际不匹配**：直接取“最新版”会导致 `checkDebugAarMetadata` 失败（新版 AAR 要求 AGP ≥ 9.1.0 / compileSdk ≥ 37）→ 已改为与 AGP 8.13.2 同代的稳定组合。
2. **尾随 lambda 绑定到 `Modifier`**：`Pill(text, active, onClick, modifier)` 的参数顺序使 `Pill("x", active = true) { … }` 的 lambda 绑到 `modifier` → 已把 `onClick` 调到最后一个参数。
3. **可空接收者**：`ApiResult.rows()` 里 `val arr: JSONArray? = … ?: return` 显式声明为可空，导致后续调用报错 → 已去掉显式可空声明。
