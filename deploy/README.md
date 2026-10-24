# 妖精论坛 ov2 部署指南（自建服务器 · 裸机）

## 架构总览

生产为**两台裸机**（生产不使用 Docker；Docker 只用于开发）：

```
Host A（公网 + WireGuard 10.8.0.1）        Host B（公网 + WireGuard 10.8.0.2）
Browser
  │ HTTPS
  ▼
Nginx (宝塔管理 80/443)
  ├── /ov2/api/*      → Go 后端  127.0.0.1:8090（canonical；SSE 单独 location）
  ├── /api/*          → Go 后端  127.0.0.1:8090（/api/v1 别名 + 旧 APP 兼容层）
  ├── /avatar/*       → Go 后端  127.0.0.1:8090（旧头像兼容）
  ├── /static/*       → Next.js  127.0.0.1:3000（旧帖图/默认头像兼容）
  └── 其余            → Next.js  127.0.0.1:3000

SeaweedFS 原生进程（systemd）10.8.0.1:8333 ◄──── WG ──── admin 写 S3
```

> 新媒体统一经 ouo `/ov2/api/media/<id>` 代理；字节存 SeaweedFS（S3），元数据存 PG。ouo/admin 前端都经 ouo 取图。
> SeaweedFS 为原生二进制 + systemd（**不是容器**），安装与升级见 `deploy/native/README.md` 与 `docs/runbook-s3-prod.md`。

- **渲染层**：Next.js（standalone 产物，Node 直跑）
- **服务层**：Go（编译二进制，systemd 管理）
- **管理端**：yj-forum-admin（Host B；会馆图片存储与入馆申请审批；图片统一由论坛 `/ov2/api/media/<id>` 直出，后台自身接口仅供预览与历史迁移）
- **数据库**：开发 = 本机 Docker PGSQL；生产 = **用户提供的外部 PGSQL**（`DATABASE_URL`）
- **对象存储**：生产 = 原生 SeaweedFS 4.47（Host A）；开发 = `make s3-up`（Docker）

## 一、数据库准备

**开发（本机 Docker）**：
```bash
make db-up    # 一键：Docker 未运行时自动拉起 Docker Desktop，容器幂等创建/启动
```
手动等价操作：
```bash
docker run -d --name ouo-postgres \
  -e POSTGRES_PASSWORD=localdev123 -e POSTGRES_DB=yj_forum \
  -p 5432:5432 postgres:18
docker exec ouo-postgres psql -U postgres -c "CREATE DATABASE yj_forum;"  # 若不存在
```
> 本机 Docker 为 Docker Desktop：`make db-up` / `make dev` 会自动确保其运行
> （优先 `systemctl --user start docker-desktop`，回退 `docker desktop start`）。

**生产（外部 PGSQL）**：无需容器，将连接串写入 `server/.env` 的 `DATABASE_URL`。
首次启动时 Go 自动执行 golang-migrate 创建全部表（共 20 张，含 sessions 与 7 张会馆系列表；旧 world 表已移除）。

## 一·五、SeaweedFS（新媒体 S3）

**生产（Host A，原生二进制 + systemd，不使用 Docker）**

```bash
# 1) 先建好 WireGuard（10.8.0.1 / 10.8.0.2），见 deploy/wireguard/
bash deploy/native/preflight.sh                 # 只读，先看兼容性结论
sudo bash deploy/native/install-weed.sh --apply --version=4.47 --sha256=<官方发布 sha256>
systemctl status seaweedfs
```

- 数据 `/var/lib/seaweedfs/data`，配置 `/etc/seaweedfs/s3.json`，单元 `seaweedfs.service`。
- 只监听 `10.8.0.1:8333`（S3）与 `9327`（指标）；公网不开放，Host B 经 WireGuard 访问。
- 完整步骤、升级、回滚与排障见 `deploy/native/README.md`、`docs/runbook-s3-prod.md`。

**开发（Docker，仅本机）**

```bash
make s3-up       # docker compose（deploy/seaweedfs/docker-compose.dev.yml），127.0.0.1:8333
make s3-status
```

- 配置见 `deploy/seaweedfs/README.md` 与 `deploy/seaweedfs/s3.json.example`。
- ouo/admin 的 `.env` 设置同一组 `S3_*`；`S3_ENABLED=false` 时新媒体落本地，旧资源始终可读（生产**不允许**静默回退，见下）。
- 数据目录 `deploy/seaweedfs/data` 只属于开发环境；生产数据在 `/var/lib/seaweedfs/data`。

## 二、后端部署（Go）

```bash
cd /opt/yj-forum
make setup                # 生成 server/.env（编辑：DATABASE_URL / SECRET_KEY / SMTP_*）
make server-build         # 编译 server/bin/yj-forum
cp deploy/yj-forum.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now yj-forum
systemctl status yj-forum
```

> 迁移 SQL 已嵌入二进制：起动时自动执行，不依赖工作目录/迁移文件；首次可使用 `make db-up` 拉起开发数据库。
> 迁移失败会直接终止启动（fail-fast，避免缺表/缺列打挂读接口），日志为 `[FATAL] 数据库迁移失败，服务退出`。

> **上传目录（`MEDIA_DIR`）**：用户上传的发帖图片存放目录，默认 `/var/yj-forum/media`（开发为 `server/data/media`，见 `server/.env`）。
> 服务首次上传时会自动创建目录（`os.MkdirAll`）；生产建议部署时预建并授予运行用户写权限（systemd 示例 `User=yoyo`，按实际部署调整）：
> ```bash
> mkdir -p /var/yj-forum/media
> chown yoyo:yoyo /var/yj-forum/media   # 改为实际运行用户
> ```

## 三、前端部署（Next.js）

```bash
cd /opt/yj-forum/web
git pull
pnpm install
# 构建时确定：rewrites 的 API_TARGET 会写进路由清单，构建后再改无效
API_TARGET=http://127.0.0.1:8090 pnpm build   # 产出 .next/standalone

cp /opt/yj-forum/deploy/yj-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now yj-web
```

> **静态资源打包已自动化**：`pnpm build` 会触发 `postbuild` → `web/scripts/prepare-standalone.mjs`，把 `public/` 与 `.next/static/` 复制进 `.next/standalone/`（幂等，可重复执行）。
> 不再需要手工 `cp`；若手工补做，必须使用 `cp -a src/. dst/` 形式（直接 `cp -r public <dest>/public` 会嵌套成 `public/public`）。
>
> ⚠️ **本步骤不可用 `next start` 替代**：systemd 跑的是 `.next/standalone/server.js`，它只服务**自身目录**内的文件（`/_next/static/*` → `standalone/.next/static/`，`/assets/*` → `standalone/public/`）。
> 漏打包的典型症状：**首页 HTTP 200，但所有 JS/CSS/图片 404**（Next 返回 9 字节纯文本 `Not Found`，且 `cache-control: no-store`）。
> 排查：`ls .next/standalone` 应有 `public/`；`ls .next/standalone/.next` 应有 `static/`。巡检脚本 `deploy/ops/check-web.sh` 已入驻 yj-ops 定时任务，会在 5 分钟内告警。

> Next.js standalone 部署说明：
> - `pnpm build` 后 `.next/standalone/server.js` 为独立运行入口；`public/` 与 `.next/static/` 由 `postbuild` 自动复制进 standalone 目录（见上）。
> - standalone 运行时只读取**自身目录**下的 `.env`（实测：`web/.env` 不会被读取）；systemd 单元用 `EnvironmentFile=/opt/yj-forum/web/.env` 注入进程环境，手动裸跑需先 `set -a; . ./.env; set +a`，或把 `.env` 放进 `.next/standalone/`。
> - `API_TARGET` 除作为 rewrites 目标（构建时固化）外，还供服务端 SSR/SEO 直连后端（运行期读取）；`NEXT_PUBLIC_API_BASE` 与 `SITE_URL` 的预渲染部分在构建期固化。

### 会馆 / 指南图片（媒体直出）

会馆 logo、馆长与会馆介绍页图片、指南正文图片统一存 SeaweedFS（S3），元数据存 PG `media_assets`；论坛前端直接请求 `/ov2/api/media/<media_id>`（`media_id` 以 `MD` 开头）。

- ouo 的会馆列表与详情接口下发 `logo_file_id`，前端拼 `/ov2/api/media/<id>`；旧 GridFS 文件（24 位 ObjectID）无法直出，前端回退占位图（按约定接受 404，待后续数据迁移）。
- 历史富文本（会馆介绍/馆长页/指南/公告等）中的 `/guild-img/...`、`/guide-img/...` 逻辑路径由 `RichContent` 渲染时重写为媒体直出地址；旧 ObjectID 文件仍按 404 处理。
- `/guild-img/*`、`/guide-img/*` 代理（Next.js rewrites 与 Nginx location）已退役；管理端的相关接口仅保留给后台预览与历史数据迁移。

## 四、Nginx 反代

1. 宝塔面板创建站点（域名绑定）。
2. 将 `deploy/nginx/yj-forum.conf` 内容合并入站点配置（注意替换 `server_name` 为实际域名）。
3. 无需再配置 `/guild-img/`、`/guide-img/` 反代（已退役，图片走 `/ov2/api/media/`）。
4. 媒体上传（`POST /ov2/api/media/images`，图片 ≤5MB；头像 ≤10MB）需 Nginx/反代允许较大请求体：配置已在 `location /ov2/api/` 与 `location /api/` 内置 `client_max_body_size 12m;`，若在 http 层统一配置请核对（不足会返回 413）。
5. SSE 必须走 `location = /ov2/api/world/stream` 与 `location = /ov2/api/messages/stream` 的专用配置（`proxy_buffering off`、`proxy_read_timeout 3600s`、`gzip off`），否则会出现“连上但不流动”。
6. 宝塔内申请 SSL 证书，开启 HTTPS（注释段提供 443 示范）。

## 五、验证

```bash
# 健康检查
curl http://127.0.0.1:8090/api/v1/votes/version/stats
curl -I http://127.0.0.1:3000/
# 浏览器访问域名，完成注册 → 登录 → 发帖全流程
```

## 六、环境变量速查

| 变量 | 位置 | 说明 |
|---|---|---|
| `DATABASE_URL` | server/.env | 数据库连接串（开发=本机 Docker，生产=外部 PGSQL） |
| `SECRET_KEY` | server/.env | Session 签名密钥（生产必须强随机） |
| `SMTP_*` | server/.env | 邮件发送（注册验证码/重置密码/通知） |
| `CORS_ORIGINS` | server/.env | CORS 白名单（生产建议配置域名） |
| `AVATAR_DIR` | server/.env | 头像存储目录 |
| `MEDIA_DIR` | server/.env | 旧用户媒体存储目录（S3 未启用时新上传也落此）；默认 `/var/yj-forum/media`；需可写 |
| `S3_ENABLED` / `S3_ENDPOINT` / `S3_BUCKET` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | server/.env（ouo + admin） | SeaweedFS S3；新上传写 S3；未启用回退本地/GridFS |
| `ALTCHA_ENABLED` / `ALTCHA_HMAC_KEY` | server/.env | ALTCHA v2；启用时登录/注册/发码/重置/Bug 提交需要 challenge/grant |
| `LEGACY_TOKEN_TTL_HOURS` / `LEGACY_APP_SUNSET` | server/.env | 旧 APP 兼容层的 token 窗口与下线日期 |
| `GITHUB_TOKEN` | server/.env | 下载页 GitHub Releases 可选 token（提高限额） |
| `PUBLIC_BASE_URL` | server/.env | 邮件中链接的站点地址 |
| `API_TARGET` | web/.env | Next rewrites 的 Go 地址（构建时写进路由清单）兼服务端 SSR/SEO 直连地址（运行期读取；生产由 Nginx 分发 API） |
| `SITE_URL` | web/.env | 站点规范域名（SEO：canonical / sitemap.xml / robots.txt / Open Graph；默认 `https://yjlt.top`，回退 `NEXT_PUBLIC_SITE_URL`，非法值自动回退）。注意：预渲染页在构建期固化（建议构建前配置），动态详情页与 sitemap 运行期生效 |
| `PORT` | web/.env | Next.js 监听端口（默认 3000） |
