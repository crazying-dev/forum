# 妖精论坛 ov2 部署指南（自建服务器 · 裸机）

## 架构总览

```
Browser
  │ HTTPS
  ▼
Nginx (宝塔管理 80/443)
  ├── /api/*      → Go 后端  127.0.0.1:8090
  ├── /avatar/*   → Go 后端  127.0.0.1:8090
  ├── /guild-img/* → 管理端 admin 127.0.0.1:8080（会馆 logo）
  └── 其余        → Next.js  127.0.0.1:3000
```

- **渲染层**：Next.js（standalone 产物，Node 直跑）
- **服务层**：Go（编译二进制，systemd 管理）
- **管理端**：yj-forum-admin（会馆 logo 存储与入馆申请审批；仅 `/guild-img/*` 对外反代）
- **数据库**：开发 = 本机 Docker PGSQL；生产 = **用户提供的外部 PGSQL**（`DATABASE_URL`）

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

## 三、前端部署（Next.js）

```bash
cd /opt/yj-forum/web
pnpm install
pnpm build                    # 产出 .next/standalone
# 复制 standalone 产物（含 public/.next 静态文件）
cp -r .next/standalone/* .next/standalone/../ 2>/dev/null || true
mkdir -p .next/standalone && cp -r public .next/standalone/ && cp -r .next/static .next/standalone/.next/

cp /opt/yj-forum/deploy/yj-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now yj-web
```

> Next.js standalone 部署说明：`pnpm build` 后 `.next/standalone/server.js` 为独立运行入口；
> 需将 `public/` 与 `.next/static/` 复制到 standalone 目录内（见上）。

### 会馆 logo 代理（ADMIN_TARGET）

会馆 logo 由管理端 yj-forum-admin 存储（GridFS），ouo 前端固定请求 `/guild-img/guilds/{id}/logo?v={logo_version}`，两种环境分别处理：

- **开发（Next.js rewrites）**：`next.config.ts` 将 `/guild-img/*` 重写到 `ADMIN_TARGET`（默认 `http://127.0.0.1:8080`），转发目标为 `${ADMIN_TARGET}/api/*`；管理端不在本机时在 `web/.env` 设 `ADMIN_TARGET=http://<admin-host>:<port>` 即可。
- **生产（Nginx）**：由 `deploy/nginx/yj-forum.conf` 的 `location /guild-img/` 直接反代到管理端（示例 `proxy_pass http://127.0.0.1:8080/api/;`，需按实际部署地址调整；也支持 upstream 写法，见配置内注释）。请求先命中 Nginx 规则，不再落到 Next.js 代理。

## 四、Nginx 反代

1. 宝塔面板创建站点（域名绑定）。
2. 将 `deploy/nginx/yj-forum.conf` 内容合并入站点配置（注意替换 `server_name` 为实际域名）。
3. 按实际部署地址校对 `location /guild-img/` 的 `proxy_pass`（默认 `http://127.0.0.1:8080/api/` 指向本机管理端）。
4. 宝塔内申请 SSL 证书，开启 HTTPS（注释段提供 443 示范）。

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
| `PUBLIC_BASE_URL` | server/.env | 邮件中链接的站点地址 |
| `API_TARGET` | web/.env | 开发时 Next 代理的 Go 地址（生产由 Nginx 分发） |
| `ADMIN_TARGET` | web/.env | 会馆 logo 代理的管理端地址（默认 `http://127.0.0.1:8080`，仅开发/未配 Nginx 时生效） |
| `SITE_URL` | web/.env | 站点规范域名（SEO：canonical / sitemap.xml / robots.txt / Open Graph；默认 `https://yjlt.top`，回退 `NEXT_PUBLIC_SITE_URL`，非法值自动回退）。注意：预渲染页在构建期固化（建议构建前配置），动态详情页与 sitemap 运行期生效 |
| `PORT` | web/.env | Next.js 监听端口（默认 3000） |
