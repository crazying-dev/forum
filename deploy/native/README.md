# SeaweedFS 原生部署（生产不使用 Docker）

> 适用：Host A（ouo + SeaweedFS）。生产版本 **4.47**，原生二进制 + systemd。
> 开发环境仍用 Docker：`deploy/seaweedfs/docker-compose.dev.yml`（只绑 `127.0.0.1:8333`）。
> 生产 S3 只绑 WireGuard 内网 `10.8.0.1:8333`，指标 `9327`，公网一律不开放。

## 1. 本目录文件

| 文件 | 用途 |
|---|---|
| `preflight.sh` | 只读前置检查（OS/架构/glibc/systemd/端口/磁盘/内存/SELinux/既有服务） |
| `install-weed.sh` | 安装/升级 SeaweedFS（默认 dry-run，`--apply` 才执行） |
| `uninstall-weed.sh` | 卸载（默认保留数据，`--purge` 才删） |
| `seaweedfs.service` | 加固后的 systemd unit（安装脚本会复制到 `/etc/systemd/system/`） |
| `s3.json.example` | 两个 identity（ouo / admin）的 S3 凭据模板，动作仅限 `yj-forum` |

## 2. 拓扑与约定

```
Host A（公网）                                Host B（公网）
┌────────────────────────────┐   WireGuard   ┌────────────────────┐
│ nginx :80/443              │   10.8.0.0/24 │ nginx → admin SPA  │
│ yj-forum :8090             │◀─────────────▶│ yj-admin :8080     │
│ yj-web   :3000             │               │ MongoDB（原生）     │
│ SeaweedFS 4.47             │               │                    │
│  S3   10.8.0.1:8333        │               │                    │
│  metrics 127.0.0.1:9327    │               │                    │
└────────────────────────────┘               └────────────────────┘
```

| 项 | 值 |
|---|---|
| 系统用户 | `seaweedfs`（nologin） |
| 二进制 | `/opt/seaweedfs/<version>/weed`，软链 `/usr/local/bin/weed` |
| 数据 | `/var/lib/seaweedfs/data`（`ReadWritePaths` 只放行此处） |
| 配置 | `/etc/seaweedfs/s3.json`（`root:seaweedfs`，0640） |
| bucket | `yj-forum`（单 bucket，前缀见下） |
| 服务 | `systemd`：`seaweedfs.service`（`Requires=wg-quick@wg0.service`） |

对象前缀（按 scene）：`post_image/`、`comment_image/`、`world_message/`、`chat_message/`、`avatar/`（ouo）；`guild_logo/`、`guild_leader_image/`、`guild_intro_image/`、`guide_image/`、`feedback_attachment/`（admin）。变体为同前缀下的 `<id>@480.jpg`、`<id>@1280.jpg`。

## 3. 首次安装

### 3.1 前置

1. Host A 已按 [`../wireguard/README.md`](../wireguard/README.md) 建立 `wg0`，本机地址 `10.8.0.1/24`；
2. 已安装 `wireguard-tools`，`systemctl status wg-quick@wg0` 为 active；
3. root 权限，已安装 `curl`、`tar`、`sha256sum`（preflight 会检查）。

### 3.2 只读预检

```bash
cd /opt/yj-forum            # 或本仓库 yj-forum-ouo 目录
bash deploy/native/preflight.sh; echo "exit=$?"
```

- `exit 0` SUPPORTED：继续；
- `exit 2` MANUAL_REVIEW：逐条看原因（例如内核/防火墙/无 wg0）；
- `exit 3` UNSUPPORTED：**不要安装**，先解决（端口被非 weed 进程占用、无 systemd、架构不支持等）。

> 全新主机在 WireGuard 尚未建立时会因 `wg0` 不存在返回 `2`（MANUAL_REVIEW）；按第 3.1 节建好 wg0 后再跑一次，期望 `exit 0`。

### 3.3 安装包校验值（SHA256）

官方 release 只提供 `.md5`，因此脚本在未传 `--sha256` 时会报错。推荐先在可信环境核对后传入：

```bash
VERSION=4.47
cd /tmp
curl -fLO "https://github.com/seaweedfs/seaweedfs/releases/download/${VERSION}/linux_amd64.tar.gz"
curl -fLO "https://github.com/seaweedfs/seaweedfs/releases/download/${VERSION}/linux_amd64.tar.gz.md5"
md5sum -c "linux_amd64.tar.gz.md5"          # 先对官方 md5
sha256sum linux_amd64.tar.gz                 # 把这一行作为 --sha256
```

离线/内网：把 tar.gz 拷到 Host A，用 `--archive=/path/linux_amd64.tar.gz --sha256=<hex>`。

### 3.4 安装

```bash
# 1) 先看计划（默认 dry-run，不改系统）
bash deploy/native/install-weed.sh --version=4.47 --sha256=<64位hex>

# 2) 执行
sudo bash deploy/native/install-weed.sh --apply --version=4.47 --sha256=<64位hex>
```

首次执行会在 `/etc/seaweedfs/s3.json` 生成占位符配置并**主动中止**（避免用占位符密码启动服务）：

```bash
sudoedit /etc/seaweedfs/s3.json      # 把 <CHANGE_ME_*> 换成强随机 accessKey/secretKey（两套）
# 重新执行安装（幂等，不会覆盖已改好的 s3.json）
sudo bash deploy/native/install-weed.sh --apply --version=4.47 --sha256=<64位hex>
```

### 3.5 验证

```bash
systemctl status seaweedfs --no-pager
journalctl -u seaweedfs -n 50 --no-pager

# 未签名请求返回 403 才是正常（说明 S3 gateway 在跑）
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/
# 指标
curl -s http://127.0.0.1:9327/metrics | head
# bucket
printf 's3.bucket.list\n' | weed shell -master=10.8.0.1:9333 | grep yj-forum
```

### 3.6 应用侧配置（ouo / admin 的 `.env`）

```env
S3_ENABLED=true
S3_ENDPOINT=http://10.8.0.1:8333
S3_REGION=us-east-1
S3_BUCKET=yj-forum
S3_ACCESS_KEY=<s3.json 中 yj-forum 的 accessKey>
S3_SECRET_KEY=<s3.json 中 yj-forum 的 secretKey>
S3_USE_PATH_STYLE=true
```

Host B 的 admin 使用 `yj-forum-admin` identity；`S3_ENDPOINT` 同样指向 `http://10.8.0.1:8333`（经 WireGuard）。

## 4. 升级

```bash
# 1) 备份数据（见第 7 节）
# 2) 预检 + dry-run
bash deploy/native/preflight.sh
bash deploy/native/install-weed.sh --version=<新版本> --sha256=<新hex>
# 3) 执行（会自动替换软链并 restart，旧版本目录保留）
sudo bash deploy/native/install-weed.sh --apply --version=<新版本> --sha256=<新hex>
# 4) 验收：上面 3.5 全部命令 + 一次真实上传/读取
```

## 5. 回滚

```bash
# 查看已安装版本
ls -1 /opt/seaweedfs/
# 切回旧版本（数据格式一般向后兼容；跨大版本前先备份）
sudo ln -sfn /opt/seaweedfs/<旧版本>/weed /usr/local/bin/weed
sudo systemctl restart seaweedfs
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/   # 期望 403/200
```

## 6. 卸载

```bash
bash deploy/native/uninstall-weed.sh                      # 看计划
sudo bash deploy/native/uninstall-weed.sh --apply         # 停服务、删 unit/二进制，保留数据与配置
sudo bash deploy/native/uninstall-weed.sh --apply --purge # 连 /var/lib/seaweedfs 与 /etc/seaweedfs 一起删
```

## 7. 备份 / 恢复

- 备份对象：`/var/lib/seaweedfs/data` + `/etc/seaweedfs/s3.json`；
- 建议先 `systemctl stop seaweedfs`（或低峰期），再快照整个 data 目录；
- 恢复：停服务 → 还原目录（保持 `seaweedfs:seaweedfs` 属主）→ 启动；
- 同时备份 PG（媒体元数据）与 admin 旧 GridFS（旧资源仍可能被读取）。

```bash
sudo systemctl stop seaweedfs
sudo tar -C /var/lib/seaweedfs -czf /backup/seaweedfs-$(date +%F).tar.gz data
sudo systemctl start seaweedfs
```

## 8. 排障

| 现象 | 排查 | 处理 |
|---|---|---|
| `systemctl start` 报依赖失败 | `systemctl status wg-quick@wg0` | 先起 WireGuard；unit 里 `Requires=wg-quick@wg0.service` |
| 启动即退出、日志 `bind: cannot assign requested address` | `ip addr show wg0` | wg0 没有 `10.8.0.1/24`，或 `--bind-ip` 与实际不符 |
| 日志 `address already in use` | `ss -ltnp \| grep -E '8333\|9327'` | 停掉占用进程（注意区分 127.0.0.1 的 dev Docker） |
| 日志 `open s3.json: permission denied` | `ls -l /etc/seaweedfs/s3.json` | 应为 `root:seaweedfs 0640`；目录 `0750` |
| 日志 `failed to load config` / JSON 解析失败 | `python3 -m json.tool /etc/seaweedfs/s3.json` | 修正 JSON 与两个 identity 的引号/逗号 |
| 应用上传 500 / AccessDenied | `journalctl -u seaweedfs -n 100`；核对 `.env` 的 key | accessKey/secretKey 不匹配，或 actions 不足 |
| 应用上传 500 / NoSuchBucket | `printf 's3.bucket.list\n' \| weed shell -master=10.8.0.1:9333` | 重跑 install 脚本第 9 步，或手动 `s3.bucket.create -name yj-forum` |
| 公网 `curl` 8333 超时 / 拒绝 | `ss -ltnp \| grep 8333` | 这是预期（只绑 10.8.0.1）；防火墙还应显式丢弃公网 8333/9327 |
| 服务被 OOM 杀（`status=9/KILL`） | `journalctl -u seaweedfs \| grep -i oom`；`systemd-cgtop` | unit 限制 `MemoryMax=768M` + `GOMEMLIMIT=640MiB`；降低 volume 数或调大限制并评估主机内存 |
| SELinux 拒绝 | `ausearch -m avc -ts recent` | `semanage fcontext -a -t var_lib_t '/var/lib/seaweedfs(/.*)?'` + `restorecon -Rv /var/lib/seaweedfs`（按发行版策略调整） |
| 磁盘涨满 | `du -sh /var/lib/seaweedfs/data/*`、`weed shell` 的 `volume.check.disk` | 扩容/清理；`-volume.max=20`、`volumeSizeLimitMB=512`（上限 10GB）为当前配置 |

## 9. 与开发（Docker）的区别

| 项 | 开发（Docker） | 生产（native） |
|---|---|---|
| 编排 | `deploy/seaweedfs/docker-compose.dev.yml` | systemd `seaweedfs.service` |
| 监听 | `127.0.0.1:8333` | `10.8.0.1:8333` + `9327` |
| 数据 | `deploy/seaweedfs/data` | `/var/lib/seaweedfs/data` |
| 凭据 | `deploy/seaweedfs/s3.json`（dev 默认值） | `/etc/seaweedfs/s3.json`（强随机） |
| 启动 | `make s3-up` | `systemctl start seaweedfs` |
