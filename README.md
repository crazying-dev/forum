# 妖精论坛 · Windows 客户端

「妖精论坛」官方桌面客户端。基于 **Python 3.12 + PyQt6** 原生实现，与官网 `https://www.yjlt.top` 的
网页功能保持一致，无需浏览器即可完成看帖、发帖、评论、世界频道、WIKI、桌宠等全部操作。

> 本仓库是 `forum` 仓库的 **`windows` 分支**，只包含 Windows 客户端；
> Web 前后端已移除（`main` 分支继续维护网页端）。

---

## 一、功能

| 模块 | 说明 |
|------|------|
| 认证 | 登录（昵称或邮箱）/ 注册（邮箱验证码）/ 找回密码（两步式：邮箱 → 验证码 + 新密码） |
| 首页 | 最新发布 / 随机推荐 / 综合排序 三个信息流 + 我的收藏 |
| 论坛 | 分区标签（综合/闲聊/求助/分享/创作）+ 排序 + 分页加载 |
| 帖子 | 详情（Markdown 正文）、点赞、收藏、举报、删除（作者）、分享链接 |
| 发帖 | 标题 + 分区 + Markdown 编辑/预览双标签 + 发帖须知 |
| 评论 | 楼中楼、折叠、点赞、回复、举报、删除（作者） |
| 搜索 | 帖子 / 用户 / 全部，关键词 ≥ 2 字符，支持分页 |
| 用户 | 资料卡（头像/头衔/前缀/性别/生日/年龄/简介/统计）、关注/粉丝列表、帖子/收藏/评论 |
| 我的 | 改资料（含头像上传）、改密码（仅邮箱验证码）、改邮箱（旧邮箱 + 新邮箱双重验证） |
| 世界频道 | 右侧常驻面板（3 秒轮询、可拖拽调宽 240-560、可收起）+ 独立整页 |
| WIKI | 总览 / 官方 / 个人 / 鼠标 / 鼠标 Linux 版 / Live2D 六页（与网页一致） |
| 彩蛋 | 每日一言与 `/Easter-Egg` 随机展示 |
| 其他 | 会馆列表、隐私政策、Bug 反馈、外链安全确认 |
| 外观 | 日间 / 夜间 / 跟随时间，对齐网页端配色 |
| 年制 | 无限年 ⇄ 公元年（无限元年 = 公元 1604 年），全站时间显示随之切换 |
| 鼠标指针 | 内置三套「罗小黑」指针包（普通 / 放大·动态 / 放大·静态），可在主窗口内启用，也可一键安装为 Windows 系统鼠标 |
| Live2D 桌宠 | 无边框、透明、置顶的桌面小窗，**原生渲染**（非网页）；可拖动、鼠标穿透、点击触发动作、视线跟随；模型只从网络下载一次并缓存 |
| 托盘 | 显示/隐藏主窗口、世界频道、桌宠开关、主题、年制、打开数据目录、检查更新、关于、退出 |
| 深链 | `Crforum://post/PS...`、`Crforum://user/RL...`、`Crforum://wiki?kind=live2d` 等 |
| 自动更新 | 下载安装包按「直连 → DoH 修 DNS → 公共加速 → 服务器反代」四级回退，逐级只在实际连接失败/超时时升级；校验 sha256 后静默安装并自动重启 |

---

## 二、快速开始（开发态）

```powershell
# 1. 安装依赖（Python 3.12+）
python -m pip install -r requirements.txt

# 2. 运行
python main.py

# 常用参数
python main.py --debug          # 控制台输出 DEBUG 日志
python main.py --minimized      # 启动后直接收进托盘
python main.py "Crforum://post/PS..."   # 深链直达
```

### 用户数据目录

所有本地状态都在 **`~/.Cr/forum/`**（Windows 即 `C:\Users\<你>\.Cr\forum`）：

```
~/.Cr/forum/
  account.bin          登录凭证（token / ID Cookie，与机器指纹绑定加密）
  config.json          主题 / 年制 / 导航 / 鼠标 / 桌宠 / 窗口位置 / 打开次数（启动支持弹窗用）
  cache/avatar/        头像缓存（进个人主页时会强制重新下载并覆盖）
  cache/image/         帖子内嵌图片、WIKI 图片与赞赏码缓存
  cache/post/          帖子正文与互动数据缓存（本地优先，进帖后联网刷新）
  Live2D/HEI.lpk       模型包（只下载一次）
  Live2D/HEI4.0/       解包归一化后的模型（*.model3.json + motions/）
  Live2D/model.json    模型指针（记录版本与路径）
  logs/forum_YYYYMMDD.log   运行日志（保留 14 天）
  update/manifest.json     更新源指纹记录（etag / 大小 / 上次检查时间）
  update/pending.json      已登记「退出程序时自动安装」的安装包
  update/<版本>/           每个版本的安装包（forum_setup.exe[.part]）、安装脚本与 apply_update.log
```

卸载时默认**不删除**该目录（删除请用 `uninstall.cmd /purge`）。

---

## 三、目录结构

```
forum-windows/
  main.py                  程序入口：单实例 / 深链 / OpenGL 格式 / 装配
  app/
    constants.py           全局常量（后端地址已混淆）、分区表、限值、资源路径
    crypto.py              字符串 XOR 混淆 + 本地凭证流加密（纯标准库）
    paths.py               程序/资源/数据目录解析（打包后自动适配）
    config.py              本地配置（原子写入、点号路径、变更监听）
    logger.py              按天写日志 + 信号广播给设置页的日志面板
    theme.py               亮/暗/国庆（假期限定）色板 + 全局 QSS + 文档 CSS
    yearmode.py            无限年/公元年换算与时间格式
    util.py                HTML 转义 / 外链判定 / 体积格式化 / 系统打开
    api.py                 唯一出网入口（宽松解析 / 异步 / 流式下载 / 401 广播）
    session_store.py       登录凭证持久化
    shell.py               主窗口：顶部栏 / 侧边导航 / 页面栈 / 世界频道分栏 / 后退
    deeplink.py            Crforum:// 解析与 HKCU 注册
    cursors.py             自定义鼠标指针（帧序列 / 动画 / 系统安装）
    tray.py               系统托盘
    updater.py            自动更新（分级回退下载 / sha256 校验 / 拉起安装器）
    netfallback.py        更新包下载回退：DoH 解析 + 公共加速镜像 + 服务器反代
    autostart.py          开机自启
    widgets/              可复用组件（卡片/头像/Toast/Markdown/帖子卡/评论/弹窗/世界面板）
    pages/                业务页面（home/forum/post*/search/user/profile/world/wiki/auth/settings/misc）
    live2d/               Live2D：lpk 解包移植 + provider + 原生渲染控件 + 桌宠窗口
  resources/              内置资源（图标 / WIKI 图 / 鼠标指针帧 / 致谢）
  packaging              Nuitka / PyInstaller / Inno Setup / iexpress 打包配置
  tests/                  单元与冒烟测试（自带运行器，不依赖 pytest）
```

---

## 四、测试

```powershell
python tests/run_tests.py            # 离线用例
python tests/run_tests.py --online   # 加上联网用例（会真实访问官网接口）
python tests/run_tests.py --verbose  # 打印每个用例名
```

当前共 **89+ 条用例**，覆盖：常量与资源、加密与凭证、配置读写、年制换算、时间解析、
主题与 QSS、API 语义（含「无 `success` 字段」「端点不被同名方法顶掉」等回归）、
异步回调线程、会话持久化、鼠标指针帧序列与 `.cur`/`.ani` 编码、Live2D 解包与引用完整性、
组件构建与整卡点击、评论树与折叠、路由表与深链解析。

---

## 五、打包与安装

```powershell
# 主后端：Nuitka standalone（产物含大量 .pyd/.dll，目录里没有 .pyc）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -InstallDeps

# 备用后端：PyInstaller onedir
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Backend pyinstaller
```

产物：

| 路径 | 说明 |
|------|------|
| `packaging\output\forum.dist\` | 客户端目录（`forum.exe` + 依赖 + `resources/`） |
| `packaging\output\forum_setup.exe` | 自解压安装包（iexpress） |
| `packaging\installer\output\` | Inno Setup 安装包（装了 ISCC 时优先生成） |

安装包写入的注册表（全部 HKCU，**不需要管理员**）：

* `HKCU\Software\Classes\Crforum`（`URL Protocol`）→ 支持 `Crforum://` 唤起
* `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\CrForum` → 卸载入口

详见 [packaging/README.md](packaging/README.md)。

---

## 六、实现要点与取舍

1. **后端地址不可修改**：写在 `app/constants.py` 里并以 XOR 字节保存，界面无任何修改入口；
   开发时想指向本地后端，直接改 `_BASE_BLOB` 并用 `crypto.hide()` 重新生成。
2. **宽松响应解析**：实测 `/api/posts` 不返回 `success` 字段，因此 `Result.ok` 只要求
   「HTTP < 400 且能解出 JSON」，同时保留 `success: false` 的兼容分支。
3. **服务端已知问题必须容忍**：`/INFO` 返回 500、更新端点当前 404，客户端全部优雅降级
   （设置页显示「更新服务暂不可用」而不是弹错误框）。
4. **时间口径照搬网页**：后端时间字符串不带时区时按 **UTC** 解析再换算本地显示；
   无限年 = 公元年 − 1604。
5. **`.ani` 自己做**：Qt 不支持 Windows 动画光标格式，也没有热区 API，因此指针包在入库时
   就被解析成 PNG 帧 + `manifest.json`（热区/帧序/每帧延时），运行时用 `QTimer` 逐帧重设 `QCursor`。
6. **Live2D 一律原生**（不用网页渲染）：`live2d-py` + `QOpenGLWidget`。
   ⚠️ 关键坑：**不要**给 `QSurfaceFormat` 指定 `3.3 Core/Compatibility`，某些驱动下
   Cubism 会报 `GL_INVALID_OPERATION` 并且一个像素都不输出；交给驱动默认（本机 4.6
   CompatibilityProfile）才正常。桌宠透明靠 `WA_TranslucentBackground` + 以 alpha=0 清屏。
7. **模型只下载一次**：`HEI.lpk` 从官网取一次，解密解包归一化到 `~/.Cr/forum/Live2D/`，
   之后 `ensure()` 直接命中缓存，不再联网。
8. **单实例 + 深链**：`QLocalServer` 命名管道，第二个实例把参数转发给已运行的实例后退出。
9. **异步一律回主线程**：所有阻塞调用走 `app.api.run_async`（QThreadPool + 队列信号），
   退出前 `wait_for_pending()` 等线程池收尾，避免解释器销毁阶段崩溃。
10. **打包不出现 `.pyc`**：主后端用 Nuitka `--standalone`（模块编译成 `.pyd`，Qt/live2d-py/numpy
    以 `.dll` 存在）；`build.ps1` 会打印 dll/pyd 与 pyc 数量供核对。
11. **更新安装脚本必须写成 `.cmd` 文件，而不是拼命令行**（v1.3.4 修的坑）：批处理文件里
    `for /L` 的循环变量必须是 `%%i`；用 Python 的 `%` 格式化拼字符串时 `%%` 会被折叠成
    单个 `%`，cmd 解析 `for /L %i` 会报「此时不应有 i」并**整段中断脚本**——现象就是
    「点了立即更新、程序退出了，但安装器一直不启动」。脚本统一用
    `newline=""` 原样写出（避免二次翻译出 `\r\r\n`），静默装完再手动 `start` 拉回客户端
    （Inno Setup 的 `[Run]` 段带 `skipifsilent`，`/SILENT` 下安装器不会自己拉起程序）。
12. **国庆节限定主题（v1.3.5）**：假期（本地时间 **10-01 00:00 ~ 10-07 24:00**）内
    `theme.resolve_mode()` 强制把「白天」映射为国庆浅色（暖白/米底 + 中国红 `#C8102E` + 五星金）、
    「夜间」映射为国庆深色（暗红 `#3A0D12` 底 + 亮金 `#FFD24A`）、「跟随系统」恒为国庆浅色。
    两套色板（`constants.THEME_NATIONAL_DAY_LIGHT / _DARK`）只存在于 `theme.PALETTES`，
    **设置页与托盘菜单不提供入口**；`config.json` 里的 `theme` 始终只记录用户的基础偏好，
    假期结束自动还原。判定期函数 `theme.is_national_day()`（10-08 00:00 起失效）。
13. **赞赏码三端常驻入口（v1.3.6）**：`app.widgets.promo.PromoDialog` 现在同时服务两种入口——
    **启动随机弹窗**（`manual=False`：文案带本地打开次数，按钮「以后再说」）与
    **常驻入口**（`manual=True`：固定公益文案，按钮「关闭」）。常驻入口由托盘菜单「支持作者」
    与设置页「关于」卡片按钮经 `promo.show_support()` 触发，**不掷概率、不改启动计数**。
    赞赏码仍是远端图 `constants.PROMO_QR_URL`，由 `widgets.images.image_cache` 落盘缓存，
    首次下载后离线可用；与网页端（`base.html` 里的 `data-src`）、安卓端
    （`Constants.REWARD_QR_URL`）同源同图，改图只需换图床文件、三端一起生效。
14. **更新安装不再经过 `.cmd` 中转（v1.3.7）**：「立即安装」与「退出时自动安装」都改为由
    `app.updater.schedule_install_on_exit()` 登记到 `atexit`，进程退出时用
    `subprocess.CREATE_NO_WINDOW` 直接唤起 `forum_setup.exe`（`shell=False`、标准流接空设备），
    彻底消除旧版 `apply_update.cmd` 带来的「闪黑框 / 控制台一直开着卡住不响应」。
    热替换分支（旧版裸 exe）必须等主程序退出才能覆盖自身，仍保留 `.cmd`。
    安装器侧 `CrForum.iss` 显式声明 `CloseApplications=yes`（用 Restart Manager 关掉
    仍占用 `forum.exe` 的客户端）+ `RestartApplications=no`，并去掉 `[Run]` 的
    `skipifsilent`——`/SILENT` 静默安装装完后由安装器自己拉起客户端
    （替代被移除的 `.cmd` 里那句 `start "" "%APP%"`）。
15. **V1.3.8：楼中楼评论渲染 + 自助注销账号 + 隐私政策 v2.0**：修复评论列表
    `CommentList._rebuild()` 从不调用 `set_children()`、导致楼中楼子回复完全不显示的问题
    （并对孙级回复递归渲染）；`PostDetailPage.refresh_auth()` 现在会在登录态变化后
    重算帖子 / 评论的「本人可删除」按钮可见性；设置页「关于」卡片与「我的」页新增
    「注销账号」入口（密码或邮箱验证码二选一 + 输入「注销账号」确认 + 「此操作不可恢复」
    二次确认），对接服务端 `POST /api/user/delete`；隐私政策页同步为三端唯一真源 v2.0
    （仅取 [通用] + [WIN] 段）。版本号升至 1.3.8。
16. **V1.3.9：出生日期选择器重做**：「编辑资料」里原来的 `QDateEdit` + 日历弹窗
    外观是系统默认风格、与主题不搭；现换成自写的 `BirthPicker`——年 / 月 / 日三个
    下拉框，日月联动、闰年正确，直接复用现有 `QComboBox` 主题样式（含下拉箭头与
    弹出列表）；未改动生日时不提交，「不展示出生日期」勾选后提交空值。版本号升至 1.3.9。
17. **V1.3.10：评论楼中楼压平为两层**：对「回复的回复」（第 3 层及更深）不再逐级
    缩进，而是压平到第 2 层，并在评论头部用「回复 @某人」标明它实际回复的是谁
    （仅压平项显示 @，直接回复根评论的第 2 层不显示）。版本号升至 1.3.10。
18. **V1.3.11：正文换行 / HTML 口径与 Web、Android 三端对齐**：
    * **单换行即换行**——Qt 的 CommonMark 解析器会把段落内的单个换行合并成空格
      （`line1\nline2` 显示为 `line1 line2`），而网页端 marked 配的是
      `breaks: true`。`app/widgets/markdown.py` 新增 `apply_hard_breaks()`，
      渲染前把单换行预处理成硬换行（行尾两个空格），代码围栏内部原样保留。
    * **不渲染 HTML 语法**——原先 Qt 会把 `<div>hi</div>` 直接吞成 `hi`
      （等于静默解析了 HTML）。现给 GitHub 方言叠加 `MarkdownNoHTML`，
      正文里的 HTML 标签按字面文字展示，与网页端 / 安卓端一致。
    * 安卓客户端发帖已改为原文直传（不再包装 `<p>…<br>…</p>`），
      历史 HTML 正文由服务端 `tool/content_migrate.py` 一次性还原。版本号升至 1.3.11。
19. **V1.3.12：评论 / 世界频道等用户不再被 Qt 当富文本解析**：评论、世界频道消息、
    帖子标题与摘要、个人简介此前都是 `QLabel`（默认 `AutoText`），字符串里出现
    `<div>` 这类标签时会被当成 HTML 解析掉（标签消失，甚至连带内容一起被“吃掉”），
    与「不渲染 HTML 语法」的三端口径冲突。`app/widgets/common.py` 新增
    `PlainLabel`（显式 `setTextFormat(PlainText)`，`\n` 照常换行），`Muted` /
    `Chip` / `ElidedLabel` 一并改为纯文本；帖子详情与评论、世界频道（页面 + 侧栏）、
    帖子卡片、个人主页 / 用户主页的评论与简介全部换用。版本号升至 1.3.12。
20. **V1.3.13：本地缓存统一「最多 24 小时」策略**：帖子缓存、头像 / 图片缓存、
    发布清单缓存此前要么永久保留（图片、头像），要么只有条数上限（帖子缓存
    300 条、无时效），导致换头像 / 换图 / 改正文后本地可能长期显示旧内容。
    新增 `app/cachepolicy.py`（`MAX_AGE_SECONDS = 24h`）统一口径：
    * **过期先用旧数据**——超时后仍先渲染本地旧数据（秒开、离线可用），
      随后后台静默重新拉取，拿到新数据再覆盖缓存；
    * **失败保留旧数据**——刷新失败（离线 / 4xx / 5xx）不清缓存；
    * `app/postcache.py` 新增 `is_stale()`；`app/widgets/images.py` 新增
      `ImageCache.age()/stale()`，头像、正文内嵌图片、Wiki 动图在缓存超过
      24 小时时「先显旧图 + 后台静默重取」；`app/releases.py` 的 `CACHE_TTL`
      由 600 秒统一为 24 小时（下载页仍可手动刷新）。版本号升至 1.3.13。
21. **V1.3.14：最低版本闸门（客户端侧）**：服务端发布清单新增 `min_versions`，
    客户端每次请求都携带自身平台与版本号，低于最低要求时服务端返回 `426` +
    `code="VERSION_TOO_LOW"`，客户端弹出**不可关闭**的「版本过低」弹窗：
    * 新增 `constants.CLIENT_PLATFORM` / `constants.CLIENT_HEADERS`，统一在
      `requests.Session` 默认头、`fetch_text` / `fetch_json`、图片缓存下载、
      更新包探测 / 下载处发出 `X-Client-Platform: windows` +
      `X-Client-Version: <版本>`；
    * `app/api.py` 新增 `add_version_too_low_listener()`，命中 `426`（或响应体
      `code == VERSION_TOO_LOW`）时通知一次（避免风暴式弹窗）；
    * `app/widgets/dialogs.py` 新增 `VersionTooLowDialog`（`BaseDialog` 新增
      `closable=False`）：只提供「去更新」（系统浏览器打开更新地址）与
      「退出应用」两个按钮，Esc / 标题栏关闭 / 外部点击均无效；
    * `app/shell.py` 通过 `version_blocked` 信号把工作线程的事件抛回主线程弹窗
      （服务端 `/api/app/*`、`/healthz` 与静态资源不在闸门范围内）。版本号升至 1.3.14。
22. **V1.3.15：三端人机验证（滑块拼图）**：服务端自研滑块拼图验证，登录 / 注册 /
    找回密码 / 注销账号 / 更换绑定邮箱 / 修改密码 / 邮箱验证邮件共 11 个接口加
    `@captcha_required` 校验，客户端需先完成滑块验证再提交业务请求：
    * 新增 `app/widgets/captcha.py`：`SliderCaptchaDialog` / `SliderStage`
      （纯 `QPainter` 绘制背景 + 可拖动拼图块 + 滑块轨道，无第三方 SDK），
      `ask_captcha(parent)` 返回一次性 token（用户取消返回 `None`，服务端关闭
      人机验证时返回空串）；
    * `app/api.py` 新增人机验证两个接口 `captcha_challenge()` /
      `captcha_verify()`，并为 10 个受保护业务方法加 `captcha_token` 参数
      （空串不写入请求体，保持旧口径）；
    * `app/pages/base.py` 新增 `Page.ask_captcha()`；登录 / 注册 / 找回密码 /
      修改密码 / 更换邮箱 / 注销账号共 10 处调用点均先弹滑块再发请求；
    * 服务端不可用时 `CAPTCHA_ENABLED=0` 一刀切关闭，客户端自动跳过弹窗。
      版本号升至 1.3.15。

---

## 七、服务端依赖

客户端只访问 `https://www.yjlt.top`，不修改服务端任何数据。以下端点被使用：

* 认证与用户：`/api/user/{login,logout,register,info,password,email,avatar/upload,<id>,<id>/follow,<id>/{posts,favorites,following,followers,comments}}`
* 邮箱验证码：`/api/email/{send-register-code,send-verify-code,verify-code-email,send-code-reset-password,reset-password-by-code,send-change-password-code,send-change-email-code,send-change-email-old-code,send-delete-account-code}`
* 人机验证（滑块拼图）：`/api/captcha/{challenge,verify}`
* 帖子与评论：`/api/posts*`、`/api/comments/*`、`/api/users/me/replies`
* 其他：`/api/world/{ALL,Send}`、`/api/search`、`/api/huiguan`、`/api/report-bug`、`/Easter-Egg`、`/healthz`
* 更新包反代（客户端四级回退的最后一级）：`/api/app/mirror/windows/<文件名>`——服务端实时拉取
  发布清单里的 GitHub 直链并流式转发，透传 `Range` 以支持断点续传
* 静态资源：`/static/live2d/HEI.lpk`、`/static/mouse/Liunx/*`、`/static/live2d/gif/*`

缺邮件服务时注册/改密/改邮箱会提示服务端返回的原因（`503 邮件服务暂不可用…`），功能本身不会崩。

---

## 八、致谢

* 鼠标指针素材：**漓翎_cub / RMWCP**（见 `resources/docs/mouse_credits.md`，非商用）
* Live2D 模型作者：**@盒装现烤奕潞**（见客户端 WIKI·Live2D 页）
* Live2D 渲染：`live2d-py`（第三方封装，与 Live2D Inc. 无关联）+ 官方 Cubism Native SDK

本项目为粉丝公益创作，与作品版权方无隶属关系。
