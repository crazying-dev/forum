<p align="center">
  <a href="https://www.yjlt.top"><img src="docs/assets/logo.png" width="120" alt="妖精论坛 Logo"></a>
</p>

<h1 align="center">妖精论坛 · Fairy Forum</h1>

《罗小黑战记》同人社区论坛，基于 Next.js 16 + Go 的 ov2 重构版。

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-CC%20BY--NC%204.0-6A8C89?style=flat&labelColor=444444" alt="License: CC BY-NC 4.0"></a>
  <a href="https://github.com/yoyo-ouo/yj-forum-ouo/issues"><img src="https://img.shields.io/github/issues/yoyo-ouo/yj-forum-ouo?style=flat&label=Issues&labelColor=444444&color=1F883D" alt="Issues"></a>
  <a href="https://github.com/yoyo-ouo/yj-forum-ouo/stargazers"><img src="https://img.shields.io/github/stars/yoyo-ouo/yj-forum-ouo?style=flat&label=Stars&labelColor=444444&color=eac54f" alt="Stars"></a>
  <a href="https://www.xiaohongshu.com/user/profile/682d321b000000000a03c93b"><img src="https://img.shields.io/badge/动态-小红书-E4405F?style=flat&logo=xiaohongshu&labelColor=444444&logoColor=white" alt="小红书"></a>
  <a href="https://www.crazying-dev.top/MyWrite"><img src="https://img.shields.io/badge/-创作支持-946ce6?style=flat&logo=wechat&labelColor=444444" alt="创作支持"></a>
</p>

<p align="center">
  <a href="https://www.yjlt.top">线上站点</a> ·
  <a href="https://github.com/yoyo-ouo/yj-forum-ouo">GitHub</a> ·
  <a href="https://github.com/yoyo-ouo/yj-forum-ouo/issues">问题反馈</a>
</p>

<p align="center">
  <a href="docs/screenshots/ov2-home-2026-10.png"><img src="docs/screenshots/ov2-home-2026-10.png" width="49%" alt="ov2 首页：会馆广场与随机推荐信息流"></a>
  <a href="docs/screenshots/ov2-post-2026-10.png"><img src="docs/screenshots/ov2-post-2026-10.png" width="49%" alt="ov2 帖子详情：引用卡片、富文本与图片"></a>
</p>

<p align="center"><sub>ov2 开发预览：首页随机推荐 · 帖子详情（帖子 / 用户 / 文章引用卡片）</sub></p>

> [!IMPORTANT]
> 本项目是《罗小黑战记》的**非官方同人创作**，与寒木春华动画工作室无任何关联，未获官方授权；仅供学习、交流与非商业用途。完整声明见[文末](#非官方声明与许可)。

## 目录

- [项目介绍](#项目介绍)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [生产部署](#生产部署)
- [项目结构](#项目结构)
- [文档](#文档)
- [贡献与反馈](#贡献与反馈)
- [非官方声明与许可](#非官方声明与许可)

## 项目介绍

妖精论坛是《罗小黑战记》同人社区，尝试还原动画中妖精与人类共存的网络社区：公共广场、会馆、文章、WIKI 与世界频道。

**ov2** 是本仓库正在进行的重构预览版：从 Flask 单体迁移为「Next.js 渲染层 + Go 服务层」，PostgreSQL 持久化，图片走 S3 兼容媒体服务（可回退本地目录）。旧版 Flask 实现归档于 [crazying-dev/forum](https://github.com/crazying-dev/forum)，仅作对照，不再维护。

> [!NOTE]
> ov2 为重构预览版，尚未替换线上 legacy 站点；[线上站点](https://www.yjlt.top)目前仍运行旧版。

## 功能特性

| 模块 | 能力 |
|---|---|
| 内容 | 帖子发布 / 分类 / 随机推荐 / 点赞 / 收藏 / 举报 / 软删除；嵌套评论与评论点赞；Markdown 与富文本编辑；帖子、用户、文章引用卡片；图片上传 |
| 会馆 | 会馆广场、详情、公告、成员与馆长页；帖子 + 文章混排信息流；入馆申请（管理端审批）与退馆 |
| 信息流 | 全站「全部 / 公共广场 / 会馆」三档筛选，分类过滤与分页加载 |
| 社交 | 关注 / 粉丝 / 互关、用户主页、消息中心（赞、评论、系统通知、管理团队会话，SSE 实时未读） |
| 世界频道 | 全站公开实时聊天：SSE 推送、桌面浮窗 / 移动端弹层、富文本 + 最多 9 张图、单条 2000 字 |
| 账号与安全 | 邮箱验证码注册 / 登录 / 重置、邮箱换绑、账号注销、第三方 OAuth（TheDoorOfBings）、ALTCHA 人机验证、限流 / CSRF / SafeHTML |
| 多端 | Windows / Android / Linux / macOS 客户端下载与版本检查、PWA 安装、旧 APP 兼容层 |
| 站点体验 | 亮 / 暗主题（时段自动切换）、WIKI（官方 / 个人 / 鼠标 / Live2D）、论坛指南、更新日志、每日一言、彩蛋、RSS、版本投票、Bug 反馈 |

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 16（App Router）、React 19、TypeScript、Tailwind CSS 4、Tiptap 3 |
| 后端 | Go 1.26、Gin、pgx、golang-migrate、bcrypt |
| 数据 | PostgreSQL 18（开发 Docker / 生产外部实例）、SeaweedFS（S3 兼容媒体存储） |
| 实时与安全 | SSE、HttpOnly Session、CSRF、限流、SafeHTML、ALTCHA |
| 部署 | 自建服务器裸机、systemd、Nginx 反代、Next.js standalone |
| 管理端 | [yj-forum-admin](https://github.com/yoyo-ouo/yj-forum-admin)（会馆审批、图片存储、用户与内容管理） |

## 快速开始

### 环境要求

- Go ≥ 1.26
- Node.js ≥ 20.9、pnpm 11
- Docker Desktop（一键启动用；也可自备 PostgreSQL 18）
- 可选：SeaweedFS 或 S3 兼容存储（未配置时使用本地 `MEDIA_DIR`）

### 启动

```bash
git clone git@github.com:yoyo-ouo/yj-forum-ouo.git
cd yj-forum-ouo

make setup              # 生成 server/.env（首次运行）
pnpm -C web install     # 安装前端依赖
make dev                # Docker PGSQL + Go :8090 + Next.js :3200
```

> 使用自备 PostgreSQL 时跳过 `make dev`：先改好 `server/.env` 的 `DATABASE_URL`，再分别运行 `make server` 与 `make web-dev`。

启动后：

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:3200 |
| API（canonical） | http://localhost:8090/ov2/api |
| API（别名） | http://localhost:8090/api/v1（响应头 `Deprecation: true`） |
| 开发数据库 | postgres://postgres:localdev123@localhost:5432/yj_forum |

`make dev` 会自动拉起 Docker Desktop 并幂等创建 `ouo-postgres` 容器；后端启动时自动执行嵌入二进制的 SQL 迁移。

### 常用命令

| 命令 | 说明 |
|---|---|
| `make setup` | 生成 `server/.env` |
| `make dev` | 一键启动数据库 + 后端 + 前端 |
| `make docker-up` | 确保本机 Docker 可用（未运行时自动启动 Docker Desktop） |
| `make db-up` / `make db-down` / `make db-logs` | 管理本机 PGSQL 容器（ouo-postgres :5432） |
| `make server` / `make server-run` / `make server-build` | 后端：`go run` / 编译并运行 / 仅编译 |
| `make web-dev` / `make web-build` / `make web-start` | 前端：dev / 生产构建 / 生产运行（:3200） |
| `make vet` | `go vet` + `gofmt` 检查 |
| `make clean` | 清理编译产物 |

## 生产部署

详见 [deploy/README.md](deploy/README.md)。要点：

1. **数据库**：外部 PostgreSQL 18，连接串写入 `server/.env` 的 `DATABASE_URL`；
2. **后端**：`make server-build` 编译二进制，交给 `deploy/yj-forum.service`（systemd）；
3. **前端**：`pnpm build` 产出 `.next/standalone`，由 `deploy/yj-web.service` 运行；
4. **媒体**：SeaweedFS（S3 兼容）或本地目录，上传经 `/ov2/api/media/*` 代理；
5. **Nginx**：`/ov2/api/*`、`/api/*`、`/avatar/*` 反代 Go；其余反代 Next.js（会馆/指南图片已改为 `/ov2/api/media/<id>` 媒体直出，原 `/guild-img/*`、`/guide-img/*` 反代已退役）；
6. **管理端**：[yj-forum-admin](https://github.com/yoyo-ouo/yj-forum-admin) 独立部署，负责会馆审批、图片存储与用户 / 内容管理。

## 项目结构

```
.
├── server/                # Go 服务层
│   ├── cmd/yj-forum/      # 入口（迁移 SQL 嵌入二进制）
│   └── internal/          # auth / handler / middleware / database / cache / email / media
├── web/                   # Next.js 渲染层
│   ├── app/               # App Router 页面（首页 / 论坛 / 帖子 / 会馆 / 消息 / WIKI…）
│   ├── components/        # Header / Card / 编辑器 / 世界频道 / 引用卡片
│   ├── lib/               # API 客户端、store、SEO、Sanitize
│   └── public/assets/     # 本地化图片 / 字体 / CSS / JS / Live2D
├── deploy/                # dev.sh / systemd / Nginx / SeaweedFS
└── docs/                  # 架构 / API / 迁移 / 验收 / 截图
```

## 文档

| 文档 | 内容 |
|---|---|
| [技术架构](docs/architecture.md) | 渲染层 / 服务层职责、数据流、安全设计 |
| [API 文档](docs/api/README.md) | canonical `/ov2/api`、OpenAPI、端点索引、SSE 与媒体 |
| [迁移基线](docs/migration-baseline.md) | 0018–0027 上线前检查清单与决策树 |
| [迁移对照](docs/migration-notes.md) | legacy Flask ↔ ov2 端点映射 |
| [资产清单](docs/资产清单.md) | 外部 CDN 资源本地化映射 |
| [验收报告](docs/验收报告.md) | 新旧功能对照验收（含界面截图对比） |
| [部署指南](deploy/README.md) | Nginx + systemd + 数据库 + 媒体 |

## 贡献与反馈

欢迎提交 issue 与 PR。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全漏洞请按 [SECURITY.md](SECURITY.md) 私密上报，不要开公开 issue。

| 角色 | 联系方式 |
|---|---|
| 当前重构者 / 维护者 | [yoyo-ouo](https://github.com/yoyo-ouo)（幽悠ouo_）· QQ 339202808 · 339202808@qq.com |
| 原作者 | [crazying-dev](https://github.com/crazying-dev) · QQ 3890320020 · 3890320020@qq.com · [联系](https://www.crazying-dev.top/CommentMe) |

## 非官方声明与许可

1. 本项目为《罗小黑战记》（The Legend of Luo Xiaohei）的粉丝**非官方同人创作**（Non-official Fan-made Project）；
2. 「妖精论坛」相关 IP 归属**寒木春华动画工作室（Hanmu Chunhua Animation Studio）**所有，本项目未获得官方任何授权；
3. 本项目仅用于学习、交流和非商业用途（Non-commercial use only），严禁用于商业盈利、冒充官方或误导用户；
4. 项目代码版权归 [crazying-dev](https://github.com/crazying-dev/) 所有，基于 [CC BY-NC 4.0](LICENSE) 许可证发布。

本项目无任何商业性质，「创作支持 / 打赏」仅为自愿的创作鼓励，不与项目使用挂钩，且所有收入仅用于项目相关的资源开销，不涉及《罗小黑战记》IP 的商业利用。

[![创作支持](https://img.shields.io/badge/-创作支持-946ce6?style=flat&logo=wechat&labelColor=444444)](https://www.crazying-dev.top/MyWrite)

> 开发者的话
>
> 动漫中出现的次数并不多，所以会出现一部分的不对应，希望大家可以理解一下。
>
> 算了，你们肯定不会理解我的，所以我给你们准备了惊喜。
