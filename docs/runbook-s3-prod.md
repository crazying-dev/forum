# SeaweedFS 生产上线 Runbook（不使用 Docker）

> 适用：yj-forum-ouo / yj-forum-admin 生产环境从「本地/GridFS」切换到 SeaweedFS S3。
> 生产不使用 Docker；开发仍用 Docker（`deploy/seaweedfs/docker-compose.dev.yml`）。
> 相关文件：`deploy/native/`（安装/unit/卸载）、`deploy/nginx/yj-forum.conf`、`deploy/ops/`。
>
> ⚠️ **2026-10-24 方案变更**：Host A 位于 NAT 后、WireGuard 无法建立，网络改为
> **公网直连：SeaweedFS 只绑 `127.0.0.1` + Nginx TLS 反代 + IP 白名单**。
> 下文所有 `10.8.0.1` 相关描述与 WireGuard 章节**仅作备选**，以本节与 `deploy/native/README.md` 为准。

## 1. 拓扑与关键约定

```
                        公网
                          │
   Host A（NAT 后，公网 154.219.110.63）   Host B（公网）
   nginx :80/:443                          nginx :80/:443（admin SPA）
     └─ s3.yjlt.top（TLS + allow B）         yj-admin :8080
          └─ http://127.0.0.1:8333           MongoDB（原生）
   yj-forum :8090
   yj-web   :3000
   SeaweedFS 4.47
     S3       127.0.0.1:8333（仅回环）
     metrics  127.0.0.1:9327
        │                                   │
        └──────── WireGuard wg0 ────────────┘
              51820/udp，AllowedIPs=/32
```

- S3 与指标**只**监听 `10.8.0.1`，公网不开放；Host B 的 admin 经 `10.8.0.1:8333` 访问 S3。
- 原 Host A 的 nginx 经 `10.8.0.2:8080` 访问 admin（`/guild-img/`、`/guide-img/`）的图片反代已退役；图片统一经 `/ov2/api/media/<id>` 直出。
- 媒体字节在 SeaweedFS，元数据在 PG（`media_assets` 等）；旧本地文件/GridFS 保持只读兼容。
- 生产 S3 数据：`/var/lib/seaweedfs/data`；配置：`/etc/seaweedfs/s3.json`。

## 2. 上线前检查清单

| 项 | 要求 |
|---|---|
| 系统 | Debian/Ubuntu 或 RHEL 系，systemd ≥ 232，x86_64/arm64 |
| 磁盘 | 根盘**可用 ≥ 15G**；SeaweedFS 上限 10G（512MB×20），Nginx 媒体缓存 3G |
| 内存 | ≥ 2G（unit `MemoryMax=768M` + `GOMEMLIMIT=640MiB` + ouo + node；低于 2G 需评估） |
| 端口 | 公网只开 22/80/443/51820udp；8333/9327/8080 不对公网 |
| 时间 | 两台主机 NTP 同步（S3 签名对时间敏感） |
| 备份 | PG 全量备份 + `/var/lib/seaweedfs`（首次为空）+ admin GridFS |
| 凭据 | `s3.json` 两套强随机 key；应用 `.env` 同步 |

## 3. 上线顺序

### Step 0 — Host A 预检

```bash
cd /opt/yj-forum          # 或仓库 yj-forum-ouo
bash deploy/native/preflight.sh; echo "exit=$?"
```

- `0` SUPPORTED → 继续；
- `2` MANUAL_REVIEW → 按输出逐条确认（wg0 未建、SELinux Enforcing、磁盘偏紧等）；
- `3` UNSUPPORTED → 停止，先解决（端口被占、无 systemd、架构不支持）。

> 全新主机此时 `wg0` 还没建，通常会返回 `2`；Step 1 完成后重跑一次，期望 `exit 0`。

### Step 1 — WireGuard（两台）

按 [`../deploy/wireguard/README.md`](../deploy/wireguard/README.md)：

```bash
# 两台
sudo install -m 0600 deploy/wireguard/wg0-host-a.conf.example /etc/wireguard/wg0.conf  # Host A
sudo install -m 0600 deploy/wireguard/wg0-host-b.conf.example /etc/wireguard/wg0.conf  # Host B
# 替换 <...> 后
sudo systemctl enable --now wg-quick@wg0

# 验证
sudo wg show                 # 两端都应有 latest handshake
ping -c 3 10.8.0.2           # Host A → B
ping -c 3 10.8.0.1           # Host B → A
```

同时下发防火墙规则（只放行 51820/udp 与 wg0 上的 8333/9327/8080）。

### Step 2 — Host A 安装 SeaweedFS 4.47

```bash
# 2.1 取得官方包并核对（官方只提供 .md5；脚本要求显式 --sha256）
VERSION=4.47
cd /tmp
curl -fLO "https://github.com/seaweedfs/seaweedfs/releases/download/${VERSION}/linux_amd64.tar.gz"
curl -fLO "https://github.com/seaweedfs/seaweedfs/releases/download/${VERSION}/linux_amd64.tar.gz.md5"
md5sum -c linux_amd64.tar.gz.md5
sha256sum linux_amd64.tar.gz      # 记下 64 位 hex

# 2.2 dry-run 看计划（可加 --archive=/tmp/linux_amd64.tar.gz 复用刚下载的包）
cd /opt/yj-forum
bash deploy/native/install-weed.sh --version=$VERSION --sha256=<hex>

# 2.3 首次 apply（会生成 s3.json 占位符并中止）
sudo bash deploy/native/install-weed.sh --apply --version=$VERSION --sha256=<hex>

# 2.4 填真实凭据（两套 identity）
sudoedit /etc/seaweedfs/s3.json

# 2.5 重跑（幂等）
sudo bash deploy/native/install-weed.sh --apply --version=$VERSION --sha256=<hex>
```

验收：

```bash
systemctl is-active seaweedfs
ss -ltnp | grep -E '8333|9327'      # 应为 127.0.0.1:8333 / 127.0.0.1:9327
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/   # 403 或 200
curl -s http://127.0.0.1:9327/metrics | head -3
printf 's3.bucket.list\n' | weed shell -master=10.8.0.1:9333      # 应含 yj-forum
```

### Step 3 — 防火墙（两台）

见 [`../deploy/wireguard/README.md`](../deploy/wireguard/README.md) 第 5 节（nftables / ufw 二选一）。核心：

- Host A：仅 `10.8.0.2` 可访问 `8333/9327`；公网 drop。
- Host B：仅 `10.8.0.1` 可访问 `8080`；公网 drop。

验证（在 Host A）：`curl --connect-timeout 3 http://<Host A 公网 IP>:8333/` 必须超时/拒绝。

### Step 3.5 — 数据库迁移（必须先做）

> 新版本上传路径会写 `media_variants`（迁移 **0028**）。生产建议 `MIGRATE_ON_START=false`，
> 因此**必须在启动新二进制之前**单独跑一次迁移，否则变体表缺失（虽然代码已降级为只写原图 + 告警，
> 但仍会丢失变体能力）。

```bash
cd /opt/yj-forum/server
# 方式 A：用新二进制触发一次启动迁移，看到 “[DB] 迁移完成” 后 Ctrl-C
MIGRATE_ON_START=true ./bin/yj-forum
# 方式 B：用 golang-migrate CLI（与迁移文件同源）
# migrate -path internal/database/migrations -database "$DATABASE_URL" up

# 校验（必须返回 media_variants）
psql "$DATABASE_URL" -c "SELECT to_regclass('public.media_variants');"
psql "$DATABASE_URL" -c "SELECT version, dirty FROM schema_migrations;"
```

### Step 4 — ouo 服务配置 + 启动顺序

```bash
# Host A: /opt/yj-forum/server/.env
S3_ENABLED=true
S3_ENDPOINT=http://10.8.0.1:8333
S3_REGION=us-east-1
S3_BUCKET=yj-forum
S3_ACCESS_KEY=<yj-forum accessKey>
S3_SECRET_KEY=<yj-forum secretKey>
S3_USE_PATH_STYLE=true
```

```bash
sudo install -m 0644 deploy/yj-forum.service deploy/yj-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart yj-forum yj-web
systemctl status yj-forum yj-web --no-pager
```

> `yj-forum.service` 已 `After=wg-quick@wg0.service seaweedfs.service`，只保证启动顺序。
> **注意**：按既定策略，启动时 S3 探测重试 12×10s 仍失败会 `exit(1)`（不允许存储分裂），
> 由 `Restart=always` 持续重试；因此「S3 不可用」等于「论坛不启动」，这是有意为之，不是故障。

### Step 5 — Host A Nginx

```bash
# 1) 媒体缓存目录（用户按发行版：Debian/Ubuntu=www-data，RHEL=nginx）
sudo install -d -o www-data -g www-data /var/cache/nginx/ov2-media

# 2) 合并配置（注意 map/proxy_cache_path 必须在 http 级；宝塔用户单独放 conf.d）
sudo cp deploy/nginx/yj-forum.conf /etc/nginx/conf.d/yj-forum.conf
sudo nginx -t && sudo systemctl reload nginx
```

检查点：

- `/guild-img/`、`/guide-img/` 已退役，nginx 不应再配置这两个 location；
- `/ov2/api/media/` 启用 `proxy_cache media`（**3g** / inactive=30d / keys_zone=100m）；
- SSE 两个 exact location 仍在（`/ov2/api/world/stream`、`/ov2/api/messages/stream`）；
- 安全头仍在（media location 内已重复声明）。

### Step 6 — Host B（admin）

```bash
# 1) 后端二进制
cd /opt/yj-forum-admin/server && go build -o build/yj-forum-admin .

# 2) .env（MongoDB 为原生，无需安装步骤；PG 指向论坛业务库）
#    SERVER_PORT=8080、MONGO_URI、PG_URL、S3_*（使用 yj-forum-admin identity）

# 3) unit
sudo install -m 0644 deploy/yj-admin.service deploy/yj-admin-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yj-admin

# 4) 前端产物发布
cd /opt/yj-forum-admin/web && pnpm install && pnpm build
sudo systemctl restart yj-admin-web

# 5) nginx
sudo cp deploy/nginx-admin.conf.example /etc/nginx/conf.d/yj-forum-admin.conf
sudo nginx -t && sudo systemctl reload nginx
```

验证：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/ping        # 200
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.2:8080/ping        # Host A 上执行，200
```

### Step 7 — 巡检（Host A）

```bash
sudo install -d -m 0755 /usr/local/bin/yj-ops
sudo install -m 0755 deploy/ops/*.sh /usr/local/bin/yj-ops/
sudo install -m 0644 deploy/ops/yj-ops.service deploy/ops/yj-ops.timer /etc/systemd/system/
sudo install -d -m 0755 /etc/yj-ops
sudo install -m 0600 deploy/ops/mail.env.example /etc/yj-ops/mail.env   # 改真实 SMTP
sudo systemctl daemon-reload
sudo systemctl enable --now yj-ops.timer

systemctl list-timers yj-ops.timer
sudo systemctl start yj-ops.service        # 手动跑一次
journalctl -u yj-ops.service -n 50 --no-pager
```

## 4. 验收清单

| # | 检查项 | 命令（Host A 除特别说明） | 期望 |
|---|---|---|---|
| 1 | preflight | `bash deploy/native/preflight.sh` | exit 0 或 2（已确认原因） |
| 2 | WG 握手 | `sudo wg show` | 两端 latest handshake 秒级 |
| 3 | 内网连通 | Host B: `curl -s -o /dev/null -w '%{http_code}' http://10.8.0.1:8333/` | `403`/`200` |
| 4 | 公网不可达 | 外部: `curl --connect-timeout 3 http://<A公网IP>:8333/` | 超时/拒绝 |
| 5 | 服务 | `systemctl is-active seaweedfs` | `active` |
| 6 | 指标 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9327/metrics` | `200` |
| 7 | bucket | `printf 's3.bucket.list\n' \| weed shell -master=10.8.0.1:9333` | 含 `yj-forum` |
| 8 | 应用上传 | 论坛发帖带图 | 201/200，PG 有 `media_assets` 记录 |
| 9 | 媒体读取 | `curl -s -D- -o /dev/null https://yjlt.top/ov2/api/media/<id>` | `200`，`X-Cache-Status: MISS` 后为 `HIT` |
| 10 | 变体缓存 | 同 id `?w=480` 与 `?w=1280` | 各自独立缓存（key 只认 480/1280） |
| 11 | 私有不进缓存 | 聊天/私密图请求两次 | 两次都不是 `HIT` |
| 12 | 404 不缓存 | `curl -s -D- -o /dev/null https://yjlt.top/ov2/api/media/not-exist` | `404`，再次请求仍 `MISS` |
| 13 | 会馆图 | `curl -s -D- -o /dev/null https://yjlt.top/ov2/api/media/<media_id>` | 200/304 |
| 14 | 旧图路径退役 | `curl -s -o /dev/null -w '%{http_code}' https://yjlt.top/guild-img/probe` | 404（不再反代管理端） |
| 15 | SSE | 浏览器进世界频道/私信 | 消息实时到达，无「连上不流动」 |
| 16 | admin | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ping`（Host B） | `200` |
| 17 | admin 页面 | 浏览器打开 `https://admin.yjlt.top` | 登录正常，静态资源 200 |
| 18 | 巡检 | `systemctl list-timers yj-ops.timer` | 5 分钟周期，next 不为空 |
| 19 | 重启韧性 | `sudo systemctl restart seaweedfs` 后再测 8/9 | 均恢复 |
| 20 | 磁盘 | `df -h /var/lib/seaweedfs` | 使用率 < 80% |

> `X-Cache-Status` 需要响应经过 `location /ov2/api/media/`（不要在浏览器强刷带着 `Cache-Control: no-cache`，否则可能 `BYPASS`）。

## 5. 回滚

### 5.1 只回滚 SeaweedFS 版本

```bash
ls -1 /opt/seaweedfs/
sudo ln -sfn /opt/seaweedfs/<旧版本>/weed /usr/local/bin/weed
sudo systemctl restart seaweedfs
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/
```

### 5.2 回滚 nginx 媒体缓存

```bash
sudo cp /etc/nginx/conf.d/yj-forum.conf.bak /etc/nginx/conf.d/yj-forum.conf
sudo nginx -t && sudo systemctl reload nginx
# 需要时清空缓存：systemctl stop nginx && rm -rf /var/cache/nginx/ov2-media/* && systemctl start nginx
df -h /var/cache   # 确认缓存目录占用
```

### 5.3 应用回滚（回代码，不要关 S3）

> ⚠️ **不要用 `S3_ENABLED=false` 做回滚**。当前实现里 S3 provider 由该开关构造，
> 关掉后读写都拿不到 provider，**所有已存 S3 媒体会直接 404**。

```bash
# 回滚到上一版二进制/前端产物，保持 S3_ENABLED=true
sudo systemctl stop yj-forum
sudo cp /opt/yj-forum/server/bin/yj-forum.bak /opt/yj-forum/server/bin/yj-forum
sudo systemctl start yj-forum
```

`media_variants` 是纯新增表，旧版本代码不读它，回滚代码无需回滚迁移。不要删除 `/var/lib/seaweedfs/data`，否则已上传的新媒体会 404。

### 5.4 完全下线 SeaweedFS

```bash
sudo bash deploy/native/uninstall-weed.sh --apply     # 保留数据
# 确认无应用依赖后再 --purge
```

## 6. 排障表

| 现象 | 定位 | 处理 |
|---|---|---|
| `seaweedfs` 启动失败：`Failed to start ... wg-quick@wg0` | `systemctl status wg-quick@wg0` | 先修 WireGuard；unit 有 `Requires=wg-quick@wg0.service` |
| `bind: cannot assign requested address` | `ip addr show wg0` | wg0 未配置 `10.8.0.1/24`，或 `--bind-ip` 改了但 unit 没改 |
| `address already in use` | `ss -ltnp \| grep -E '8333\|9327'` | 停占用进程；注意 `127.0.0.1:8333` 的开发 Docker 不冲突 |
| 启动日志 `s3.json` 解析失败 | `python3 -m json.tool /etc/seaweedfs/s3.json` | 修 JSON；重新 `install-weed.sh --apply`（不会覆盖已有文件） |
| 应用上传 500 / `AccessDenied` | `journalctl -u seaweedfs -n 100`；核对 `.env` 与 s3.json | key 不匹配或 actions 不含 `Write:yj-forum` |
| 应用上传 500 / `NoSuchBucket` | `printf 's3.bucket.list\n' \| weed shell -master=10.8.0.1:9333` | 缺 bucket：`s3.bucket.create -name yj-forum` |
| 请求 S3 报 `SignatureDoesNotMatch` | 两台 `timedatectl` | 时间偏移 > 15min：启用 NTP（`timedatectl set-ntp true`） |
| nginx 启动报 `proxy_cache_path` 不允许 | 配置放错层级 | 把 map / proxy_cache_path 移到 http 级 conf.d |
| 媒体首次请求 500、日志 `Permission denied /var/cache/nginx/...` | `ls -ld /var/cache/nginx/ov2-media` | 目录属主改为 nginx 用户（www-data/nginx） |
| 私有图被外部看到 | 检查 `X-Media-Cache` / `Cache-Control` | 上游必须对私有资源返回 `private`；nginx 已有 map 兜底，勿删 |
| 缓存盘被写满 | `du -sh /var/cache/nginx/ov2-media` | `max_size=3g` 会自动淘汰；仍涨满则查 `proxy_cache_key` 是否异常（只应含 `$uri` + 归一化 `w`） |
| OOM（`status=9/KILL`） | `journalctl -k \| grep -i oom`；`systemd-cgtop` | `MemoryMax=1G`：评估调大或减少 volume |
| SELinux 拦截 | `ausearch -m avc -ts recent` | 配 `semanage fcontext` / `restorecon`，见 native/README |
| AppArmor 拦截 | `dmesg \| grep -i apparmor` | 为 weed/nginx 放行 `/var/lib/seaweedfs` 与 `10.8.0.1:8333` |
| `weed shell` 连不上 master | `ss -ltnp \| grep 9333` | master 绑在 10.8.0.1；`--master=10.8.0.1:9333` |
| 磁盘空间不足 | `df -h /var/lib/seaweedfs` | 扩容或清理；备份后删旧 volume（按官方流程） |

## 7. 端口 / 路径速查

| 项 | 值 |
|---|---|
| WireGuard | `10.8.0.1`（A）/ `10.8.0.2`（B），`51820/udp` |
| SeaweedFS S3 | `10.8.0.1:8333`（仅 wg0） |
| SeaweedFS metrics | `127.0.0.1:9327`（仅回环） |
| ouo Go | `127.0.0.1:8090` |
| ouo Web（Next） | `127.0.0.1:3000` |
| admin Go | `10.8.0.2:8080`（本机 nginx 反代；wg0 仅对 A 放行） |
| Nginx | `:80` / `:443` |
| 二进制 | `/opt/seaweedfs/<ver>/weed` → `/usr/local/bin/weed` |
| unit | `/etc/systemd/system/seaweedfs.service` |
| 数据 | `/var/lib/seaweedfs/data` |
| 配置 | `/etc/seaweedfs/s3.json` |
| 媒体缓存 | `/var/cache/nginx/ov2-media`（3g） |
| 巡检脚本 | `/usr/local/bin/yj-ops/*.sh` |
| 巡检配置 | `/etc/yj-ops/mail.env`、`/etc/yj-ops/ops.env`（可选） |
| admin 静态 | `/var/www/yj-forum-admin` |

## 8. 常用命令

```bash
# 服务
systemctl status seaweedfs yj-forum yj-web --no-pager
journalctl -u seaweedfs -f
systemctl restart seaweedfs

# S3 / bucket
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/
printf 's3.bucket.list\n' | weed shell -master=10.8.0.1:9333

# 巡检
systemctl start yj-ops.service && journalctl -u yj-ops.service -n 50 --no-pager

# nginx
nginx -t && systemctl reload nginx
tail -f /var/log/nginx/error.log

# WireGuard
wg show
systemctl status wg-quick@wg0 --no-pager
```

## 9. 开发环境对照（避免混用）

| 项 | 开发 | 生产 |
|---|---|---|
| S3 启动 | `make s3-up`（Docker） | `systemctl start seaweedfs` |
| S3 地址 | `127.0.0.1:8333` | `10.8.0.1:8333` |
| 数据 | `deploy/seaweedfs/data` | `/var/lib/seaweedfs/data` |
| 配置 | `deploy/seaweedfs/s3.json` | `/etc/seaweedfs/s3.json` |
| 日志 | `make s3-logs` | `journalctl -u seaweedfs` |

> 开发机上的 `127.0.0.1:8333` 不会影响生产绑定 `10.8.0.1:8333`（不同监听地址），但**不要把开发 s3.json 的开发密钥带到生产**。
