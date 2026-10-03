# 妖精论坛 (Fairy Forum)

> 《罗小黑战记》同人创作 · 仿官方妖精论坛系统
> 当前版本：**ov2**（Next.js + Go 重构版）｜旧版 Flask（1.0.24）已归档：完整代码见上游 [crazying-dev/forum](https://github.com/crazying-dev/forum)，本机工作区克隆于 `forum-legacy/`

---

## 📢 重要声明（Important Notice）

1. 本项目为《罗小黑战记》（The Legend of Luo Xiaohei）的粉丝**非官方同人创作**（Non-official Fan-made Project）；
2. 「妖精论坛」相关 IP 归属**寒木春华动画工作室（Hanmu Chunhua Animation Studio）** 所有，本项目未获得官方任何授权；
3. 本项目仅用于学习、交流和非商业用途（Non-commercial use only），严禁用于商业盈利、冒充官方或误导用户；
4. 项目代码版权归 [crazying-dev](https://github.com/crazying-dev/) 所有，基于 [CC BY-NC 4.0](LICENSE) 许可证发布。

---

[![Stars](https://img.shields.io/github/stars/yoyo-ouo/yj-forum-ouo?style=flat&label=Stars&labelColor=444444&color=eac54f)](https://github.com/yoyo-ouo/yj-forum-ouo)
[![Issues](https://img.shields.io/github/issues/yoyo-ouo/yj-forum-ouo?style=flat&label=Issues&labelColor=444444&color=1F883D)](https://github.com/yoyo-ouo/yj-forum-ouo/issues)
[![动态-小红书](https://img.shields.io/badge/动态-小红书-E4405F?style=flat&logo=xiaohongshu&labelColor=444444&logoColor=white&logoSize=auto)](https://www.xiaohongshu.com/user/profile/682d321b000000000a03c93b)
[![创作支持](https://img.shields.io/badge/-创作支持-946ce6?logo=wechat&style=flat&labelColor=444444&logoSize=auto)](https://www.crazying-dev.top/MyWrite)

![访问计数](https://count.getloli.com/@crazying-dev)

---

## 项目介绍

仿《罗小黑战记》官方妖精论坛的同人社区系统，旨在还原动画中妖精与人类共存的网络社区生态。**ov2 版本**已完成从 Flask 单体到「Next.js 渲染层 + Go 服务层」的全量重构（对照验收见 `docs/验收报告.md`）。

## 功能概览

| 模块 | 功能 |
|---|---|
| 用户 | 注册/登录/登出、邮箱验证码、密码重置、邮箱 token 验证、第三方登录（TheDoorOfBings OAuth）、资料编辑、头像上传（400×400）、关注/粉丝、封禁拦截 |
| 帖子 | 分类浏览、分页、随机推荐、Markdown 编辑预览、点赞、收藏、举报、软删除（仅作者）、SafeHTML 内容净化 |
| 评论 | 发表/回复（parent_id 嵌套）、点赞、删除（仅作者）、时间展示 |
| 搜索 | 帖子 + 用户双通道、加载更多 |
| 会馆 | 会馆广场列表与详情（馆长/成员数/分类/公告）、会馆信息流（帖子 + 文章混排与分页）、文章阅读、入馆申请与退馆（申请由管理端审批）、全站信息流三档筛选（全部/公共广场/会馆） |
| 其他 | 版本投票、Bug 举报、彩蛋、WIKI 全套（官方/个人/鼠标/Live2D）、隐私政策、PWA、主题切换（亮/暗 + 时段自动）、RSS/robots |
| 通知 | SMTP 邮件：注册验证码、密码重置、登录提醒、粉丝/评论通知、Bug 通知（异步 goroutine） |

## 技术栈（ov2）

- **后端**：Go 1.25 / Gin / pgx / golang-migrate / bcrypt（兼容旧 werkzeug 哈希）
- **前端**：Next.js 16 (App Router) / React 19 / TypeScript / Tailwind CSS 4 / pnpm
- **数据库**：PostgreSQL（开发：本机 Docker PGSQL；生产：外部 PGSQL）
- **部署**：自建服务器裸机 + systemd + Nginx 反代（前端 standalone 产物）

> 旧版 Flask 实现（1.0.24）已归档：完整代码见上游 [crazying-dev/forum](https://github.com/crazying-dev/forum)，本机工作区克隆于 `forum-legacy/`；仅作对照参考，不再维护；新版部署不再依赖 Vercel/CDN 资源（全部本地化）。

---

## 项目结构

```
├── server/          # Go 后端（Gin，/api/v1 RESTful）
│   ├── cmd/yj-forum/    # 入口（迁移 SQL 已嵌入二进制）
│   └── internal/        # auth / cache / config / database / email / handler / middleware / models
├── web/             # Next.js 前端（App Router，standalone 输出）
│   ├── app/             # 页面（首页/论坛/帖子/文章/会馆/用户/WIKI/搜索等）
│   ├── components/      # 共享组件（Header/Card/Modal/Toast 等）
│   ├── lib/             # api.ts / store.tsx（站点状态、主题）
│   └── public/assets/   # 本地化静态资源（图片/字体/CSS/JS/Live2D）
├── deploy/          # 部署：dev.sh / systemd 单元 / Nginx 配置 / 部署指南
└── docs/            # 架构 / API / 迁移对照 / 验收报告 / 资产清单 / 截图
```

---

## 快速开始（开发环境）

### 环境要求

Docker Desktop（本地 PostgreSQL，脚本自动拉起）、Go ≥ 1.25、Node.js + pnpm。

### 一键启动

```bash
make setup        # 生成 server/.env（首次运行，按需修改）
make dev          # 一键启动：Docker PGSQL + Go 后端(:8090) + Next.js(:3200)
```

启动后访问：前端 http://localhost:3200 ，API http://localhost:8090/api/v1 。

> 无需手动启动 Docker：`make dev` / `make db-up` 会自动检测并拉起本机 Docker Desktop（优先 `systemctl --user start docker-desktop`，回退 `docker desktop start`；引擎由 systemd 托管，界面异常不影响守护进程）。

### 常用命令

| 命令 | 说明 |
|---|---|
| `make setup` | 生成 `server/.env` |
| `make dev` | 一键起开发环境（数据库 + 后端 + 前端） |
| `make docker-up` | 确保本机 Docker 可用（未运行时自动启动 Docker Desktop） |
| `make db-up` / `db-down` / `db-logs` | 管理本机 PGSQL 容器（ouo-postgres :5432，自动拉起 Docker） |
| `make server` / `server-run` / `server-build` | 后端：`go run` / 编译+运行 / 仅编译 |
| `make web-dev` / `web-build` / `web-start` | 前端：dev / 生产构建 / 生产运行（:3200） |
| `make vet` | go vet + gofmt 检查 |
| `make clean` | 清理编译产物 |

> 后端启动时自动执行数据库迁移（SQL 已嵌入二进制），任意目录运行 `make server` 均可，无工作目录依赖。

---

## 生产部署

详见 [deploy/README.md](deploy/README.md)（Nginx 反代 + systemd 双服务），要点：

1. **数据库**：外部 PGSQL，连接串写入 `server/.env` 的 `DATABASE_URL`；
2. **后端**：`make server-build` 编译二进制 → `deploy/yj-forum.service` 交给 systemd；
3. **前端**：`pnpm build` 产出 `.next/standalone`，`node server.js` 运行（`yj-web.service`）；
4. **Nginx**：`/api/*`、`/avatar/*` 反代 Go(:8090)，`/guild-img/*` 反代会馆 logo 的管理端(:8080)，其余反代 Next.js(:3000)；
5. **HTTPS**：`deploy/nginx/yj-forum.conf` 内含 443 配置模板。

## 文档

- [技术架构](docs/architecture.md) — ov2 架构总览、数据流、安全设计
- [API 文档](docs/api.md) — `/api/v1` 全端点说明
- [迁移对照笔记](docs/migration-notes.md) — legacy Flask ↔ ov2 端点映射
- [资产清单](docs/资产清单.md) — 外部 CDN 资源本地化映射表
- [验收报告](docs/验收报告.md) — 新旧功能对照验收（含界面截图对比）

---

## 问题反馈与联系

**当前重构者 / 维护者**：yoyo-ouo（幽悠ouo_）
- QQ：339202808
- 邮箱：339202808@qq.com

**原作者**：crazying-dev
- QQ：3890320020
- 邮箱：3890320020@qq.com
- [在线联系方式](https://www.crazying-dev.top/CommentMe)

---

> 开发者的话：
> 动漫中出现的次数并不多
> 所以会出现一部分的不对应
> 希望大家可以理解一下
>
> 算了，你们肯定不会理解我的
> 所以我给你们准备了惊喜

---

### 非商业说明

本项目无任何商业性质，「创作支持 / 打赏」仅为自愿的创作鼓励，不与项目使用挂钩，且所有收入仅用于项目相关的资源开销，不涉及《罗小黑战记》IP 的商业利用。

[![创作支持](https://img.shields.io/badge/-创作支持-946ce6?logo=wechat&style=flat&labelColor=444444&logoSize=auto)](https://www.crazying-dev.top/MyWrite)
