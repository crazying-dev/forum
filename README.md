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
| 自动更新 | 从官网更新端点下载新版并自动替换重启 |

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
  config.json          主题 / 年制 / 导航 / 鼠标 / 桌宠 / 窗口位置等
  cache/avatar/        头像缓存
  cache/image/         帖子内嵌图片与 WIKI 图片缓存
  Live2D/HEI.lpk       模型包（只下载一次）
  Live2D/HEI4.0/       解包归一化后的模型（*.model3.json + motions/）
  Live2D/model.json    模型指针（记录版本与路径）
  logs/forum_YYYYMMDD.log   运行日志（保留 14 天）
  update/              自动更新下载与替换脚本
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
    theme.py               亮/暗色板 + 全局 QSS + 文档 CSS
    yearmode.py            无限年/公元年换算与时间格式
    util.py                HTML 转义 / 外链判定 / 体积格式化 / 系统打开
    api.py                 唯一出网入口（宽松解析 / 异步 / 流式下载 / 401 广播）
    session_store.py       登录凭证持久化
    shell.py               主窗口：顶部栏 / 侧边导航 / 页面栈 / 世界频道分栏 / 后退
    deeplink.py            Crforum:// 解析与 HKCU 注册
    cursors.py             自定义鼠标指针（帧序列 / 动画 / 系统安装）
    tray.py               系统托盘
    updater.py            自动更新
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

---

## 七、服务端依赖

客户端只访问 `https://www.yjlt.top`，不修改服务端任何数据。以下端点被使用：

* 认证与用户：`/api/user/{login,logout,register,info,password,email,avatar/upload,<id>,<id>/follow,<id>/{posts,favorites,following,followers,comments}}`
* 邮箱验证码：`/api/email/{send-register-code,send-verify-code,verify-code-email,send-code-reset-password,reset-password-by-code,send-change-password-code,send-change-email-code,send-change-email-old-code}`
* 帖子与评论：`/api/posts*`、`/api/comments/*`、`/api/users/me/replies`
* 其他：`/api/world/{ALL,Send}`、`/api/search`、`/api/huiguan`、`/api/report-bug`、`/Easter-Egg`、`/healthz`
* 静态资源：`/static/live2d/HEI.lpk`、`/static/mouse/Liunx/*`、`/static/live2d/gif/*`

缺邮件服务时注册/改密/改邮箱会提示服务端返回的原因（`503 邮件服务暂不可用…`），功能本身不会崩。

---

## 八、致谢

* 鼠标指针素材：**漓翎_cub / RMWCP**（见 `resources/docs/mouse_credits.md`，非商用）
* Live2D 模型作者：**@盒装现烤奕潞**（见客户端 WIKI·Live2D 页）
* Live2D 渲染：`live2d-py`（第三方封装，与 Live2D Inc. 无关联）+ 官方 Cubism Native SDK

本项目为粉丝公益创作，与作品版权方无隶属关系。
