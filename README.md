# 妖精论坛 · 微信小程序（`WeChat` 分支）

对接 `https://www.yjlt.top` 现有后端 API 的微信小程序客户端，使用原生小程序框架（WXML / WXSS / JS），无需构建步骤，微信开发者工具可直接打开。

> 本分支与 `main` / `windows` / `Android` / `APP` / `TurnTo` / `text` 平行，**只承载本端客户端代码**，服务端源码不在本分支内。

## 一、快速开始（微信开发者工具）

1. 打开 **微信开发者工具** → 「导入项目」。
2. **目录**：选择本目录（即 `WeChat/`，内含 `project.config.json`）。
3. **AppID**：
   - 有正式小程序 AppID 时填入自己的 AppID；
   - 无 AppID 时点击「测试号」即可（本项目 `project.config.json` 中预置了 `"appid": "touristappid"`，即游客/测试模式）。
4. 后端域名校验：本项目默认 `"urlCheck": false`（见 `project.config.json` / `project.private.config.json`），**开发期无需在后台配置域名白名单**。
5. 正式发布前，请在 **微信公众平台 → 开发 → 开发设置 → 服务器域名** 中把 `https://www.yjlt.top` 加入 **request 合法域名** 与 **uploadFile 合法域名**。

## 二、目录结构

```
WeChat/
├── project.config.json          # 开发者工具项目配置（appid / miniprogramRoot / 编译设置）
├── project.private.config.json  # 本地私有配置（已 gitignore）
├── sitemap.json                 # 索引规则
├── app.json                     # 页面注册 / tabBar / window
├── app.js                       # 全局状态（登录用户、主题、版本）
├── app.wxss                     # 全局样式与主题 CSS 变量
├── utils/
│   ├── api.js                   # 请求封装（BASE_URL / 版本头 / 426 网关 / 401 清理 / 上传）
│   ├── util.js                  # 分类表、无尽年换算、时间格式化、交互封装
│   └── theme.js                 # 主题（自动/日间/夜间 + 国庆红）切换与原生栏同步
├── components/
│   ├── post-card/               # 帖子卡片（列表复用）
│   └── captcha/                 # 滑块验证码浮层
└── pages/                       # 12 个页面
    ├── index/    首页（推荐/最新/热门/收藏）
    ├── forum/    论坛（分类 + 分页）
    ├── world/    世界频道（轮询聊天）
    ├── me/       我的（登录态 / 资料 / 入口）
    ├── detail/   帖子详情（正文 + 二级评论）
    ├── create/   发布帖子
    ├── search/   搜索（帖子 + 用户）
    ├── user/     用户主页（帖子 / 收藏）
    ├── login/    登录
    ├── register/ 注册（邮箱验证码）
    ├── settings/ 设置（主题 / 资料 / 改密 / 退出）
    └── privacy/  隐私政策
```

## 三、后端 API 对接说明

- **Base URL**：`https://www.yjlt.top`（`utils/api.js` 中 `BASE_URL`，如需切换环境只改这一处）。
- **客户端标识**：请求头 `X-Client-Platform: wechat`、`X-Client-Version: 1.0.0`。
  - 服务端版本门限 `min_versions` 目前为 `{windows, android, web}`，**未收录 `wechat`**，未知平台按放行处理（不会返回 426）。若未来服务端新增 `wechat` 门限，只需同步提升 `utils/api.js` 中 `APP_VERSION`。
- **业务响应约定**：除世界频道外，业务接口统一返回 `{ success, ... }`；HTTP 426 触发版本过低弹窗，401 触发本地登录态清理。

### 3.1 认证（重要风险点）

服务端登录态为 **Cookie-only**：登录成功后由 `Set-Cookie` 下发 `token` 与 `ID`（均为 HttpOnly），后续请求依赖浏览器/客户端自动携带 Cookie。

- 小程序 `wx.request` 内部维护 **按域名隔离的 Cookie jar** 并会自动回传，因此本客户端在常规使用下可正常工作。
- 但小程序 **无法手动读取或写入 `Cookie` 请求头**（没有 `wx.getCookie` 这类能力），所以：
  - 不做「登录态跨设备持久化」承诺，登录成功后本地仅缓存用户资料（`storage` 键 `forum-user`）用于 UI 展示；
  - 若后端未来为小程序提供 **Token 头（如 `Authorization`）** 方案，建议在 `utils/api.js` 统一注入以彻底规避该风险。

### 3.2 验证码（滑块）

服务端 `@captcha_required` 保护的端点（登录、注册、注销账号、以及 8 个 `/api/email/*`）需要 `captcha_token`。

- 网页端使用 Cloudflare Turnstile，**小程序环境无法接入**，因此本客户端统一强制 `POST /api/captcha/challenge?provider=slider` 走 **滑块**：
  - 返回 `{ success, token, bg, piece, y, width, height, piece_size, expires_in }`；
  - 组件把画布缩放到 `min(1, (屏宽-64)/原图宽)` 后交由用户拖拽；
  - 松手 `POST /api/captcha/verify { captcha_token, captcha_x }`，容差 ±12px，有效期 300s，令牌与客户端 IP 绑定；
  - **验证失败会使令牌失效**，因此失败后组件会自动重新拉取挑战并抖动提示。
- 若服务端已关闭验证码，challenge 返回 `{ success:true, enabled:false, token:"" }`，此时组件回调空串，请求 **不携带** `captcha_token`，与后端放行逻辑一致。
- `components/captcha` 的 `capture(cb)` 回调约定：`cb(null)` = 用户取消；`cb('')` = 服务端未启用；`cb('xxx')` = 已通过。

### 3.3 注册流程（两次验证码）

注册需要 **消耗两次验证码**（`/api/email/send-register-code` 与 `/api/user/register` 各一次）：

1. 用户填 `name / email / 密码 / 邮箱验证码`；
2. 点「获取验证码」→ 先过滑块 → 调 `POST /api/email/send-register-code { email, captcha_token }`；
3. 用户从邮箱取出 6 位码填入；
4. 提交 → **再过一次滑块**（新令牌）→ 调 `POST /api/user/register { name, email, password, code, captcha_token }`；成功后自动登录。

### 3.4 关键接口映射

| 功能 | 方法与路径 | 说明 |
| --- | --- | --- |
| 首页-推荐 | `GET /api/posts/random?limit=200` | 随机推荐 |
| 首页-最新 | `GET /api/posts?sort=time` | 无 `latest` 端点，用 `sort=time` |
| 首页-热门 | `GET /api/posts?sort=comprehensive` | 综合排序 |
| 首页-收藏 | `GET /api/user/<uid>/favorites` | 仅本人可见 |
| 论坛列表 | `GET /api/posts?page&page_size=20&category=` | 分页 + 分类 |
| 帖子详情 | `GET /api/posts/<id>` | 返回 `post/comments/liked/favorited` |
| 发帖 | `POST /api/posts/create` | 正文为 HTML，客户端换行转 `<br/>` 并转义 `&<>` |
| 点赞/收藏 | `POST /api/posts/<id>/like` · `/favorite` | 切换式 |
| 举报 | `POST /api/posts/<id>/report` | `{ reason, detail }` |
| 评论 | `GET /api/posts/<id>/comments` · `POST /api/posts/<id>/comments/create` | `parent_id` 组织二级 |
| 评论点赞/删除 | `POST /api/comments/<id>/like` · `/delete` | 删除仅作者 |
| 世界频道 | `GET /api/world/ALL` · `POST /api/world/Send` | **裸数组**返回，最新在前；客户端反转并保留末 200 条，3s 轮询 |
| 搜索 | `GET /api/search?k&type=both` | 帖子 + 用户 |
| 用户主页 | `GET /api/user/<id>` · `/<id>/posts` · `/<id>/favorites` | 收藏仅本人 |
| 关注 | `POST /api/user/<id>/follow` | 切换式 |
| 登录 | `POST /api/user/login` | `{ name\|email, password, captcha_token }` |
| 注册 | `POST /api/user/register` | 见 3.3 |
| 邮箱验证码 | `POST /api/email/send-register-code` 等 | 均需验证码 |
| 个人资料 | `GET/PUT /api/user/info` | PUT 白名单 `avatar,gender,age,intro,name` |
| 修改密码 | `POST /api/user/password` | 兼容 `old_password` 分支 |
| 注销账号 | `POST /api/user/delete` | 需登录 + 验证码 |

## 四、主题与时间

- **主题**：`自动 / 日间 / 夜间` 三态，另有国庆（10-01~10-07）主题；自动模式下夜间判定为 18:00–06:00（国庆期间仅在用户显式选择夜间时启用暗色）。切换时同步 `navigationBar`、页面背景与 tabBar 配色。
- **无尽年**：与网页端一致，可在设置中切换公历 / 无尽年显示（`storage` 键 `forum-year-mode`）。
- **时间**：后端时间戳为 **无时区** 的 `"YYYY-MM-DD HH:MM:SS"`，客户端按 **UTC** 解析后本地化显示（与网页端保持一致）。

## 五、开发约定

- 无构建步骤，不依赖 npm；`utils` 采用 CommonJS `require`。
- 新增页面前请在 `app.json` 的 `pages` 中登记。
- `project.private.config.json` 已被 `.gitignore` 忽略，存放个人本地偏好，请勿提交。
- 提交前建议本地做一次语法体检：

```powershell
Get-ChildItem -Recurse -File -Include *.js | ForEach-Object { node --check $_.FullName }
```

## 六、已知限制

1. **Cookie-only 登录态**（见 3.1）：依赖 `wx.request` 的域名级 Cookie jar，未做跨设备持久化；无 Token 头方案。
2. 世界频道为 3s 轮询（服务端 `Cache-Control: max-age=2`），非 WebSocket 长连接。
3. tabBar 为纯文字（未配图标），如需图标请在 `app.json` 的 `tabBar.list` 中补充 `iconPath` / `selectedIconPath`。
4. 验证码仅支持滑块；若服务端同时启用其它 provider，本端固定请求 `provider=slider`。
