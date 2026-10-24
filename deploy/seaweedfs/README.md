# SeaweedFS（S3）：开发 Docker / 生产 native

> 本目录**仅用于开发环境**：`docker-compose.dev.yml` 把 S3 绑在 `127.0.0.1:8333`。
> **生产不使用 Docker**，改用 systemd + 原生二进制（SeaweedFS 4.47，只绑 WireGuard `10.8.0.1:8333`）：
> 见 [`../native/README.md`](../native/README.md) 与 [`../../docs/runbook-s3-prod.md`](../../docs/runbook-s3-prod.md)。

| 环境 | 编排 | 监听 | 数据目录 |
|---|---|---|---|
| 开发 | `docker-compose.dev.yml` | `127.0.0.1:8333` | `deploy/seaweedfs/data` |
| 生产 | systemd `seaweedfs.service` | `10.8.0.1:8333`（+ 指标 9327） | `/var/lib/seaweedfs/data` |

## 1. 开发：启动

```bash
cd yj-forum-ouo/deploy/seaweedfs
cp s3.json.example s3.json   # 首次：改成强随机 access/secret
mkdir -p data
docker compose -f docker-compose.dev.yml up -d
```

或在仓库根：

```bash
make s3-up      # 确保数据目录 / s3.json / 容器 / bucket
make s3-status
make s3-logs
make s3-down
```

健康检查：容器内 `wget -S http://127.0.0.1:8333/` 返回 `403` 或 `200` 即视为存活（未签名请求 403 是正常的）。

## 2. 配置 ouo / admin（开发）

在 `yj-forum-ouo/server/.env` 与 `yj-forum-admin/server/.env` 中设置：

```env
S3_ENABLED=true
S3_ENDPOINT=http://127.0.0.1:8333
S3_REGION=us-east-1
S3_BUCKET=yj-forum
S3_ACCESS_KEY=<s3.json 中的 accessKey>
S3_SECRET_KEY=<s3.json 中的 secretKey>
S3_USE_PATH_STYLE=true
```

> ouo 与 admin 使用不同的 key（`s3.json.example` 已给出两个 identity），权限都只到 `yj-forum` bucket。
> 生产环境把 `S3_ENDPOINT` 换成 `http://10.8.0.1:8333`（见 native/README）。

## 3. Bucket / object key

- 单 bucket：`yj-forum`。
- 前缀（按 scene）：`post_image/`、`comment_image/`、`world_message/`、`chat_message/`、`avatar/`、`guild_logo/`、`guild_leader_image/`、`guild_intro_image/`、`guide_image/`、`feedback_attachment/`；变体为同前缀下的 `<id>@480.jpg`、`<id>@1280.jpg`。
- 私有 bucket；应用 key 只授予该 bucket 的读写列表权限；不要对公网开放 8333。

## 4. 备份 / 恢复

- 开发：数据在 `deploy/seaweedfs/data`，随容器删除不会丢，但不要提交进 Git。
- 生产：`/var/lib/seaweedfs/data` + `/etc/seaweedfs/s3.json`，详见 native/README 第 7 节。
- 备份同时覆盖 PG 与 admin 旧 GridFS（旧资源仍可能被读取）。

## 5. 故障排查

- `docker compose -f docker-compose.dev.yml logs -f` 看 S3 gateway 日志。
- `curl -i http://127.0.0.1:8333/` 返回 403 说明网关在跑（未签名请求被拒是正常的）。
- 上传 500：先确认 bucket 已创建、key 有 `Write:yj-forum` 权限、`S3_ENDPOINT` 可从服务容器/主机访问。
- 旧资源 404：确认 `MEDIA_DIR`/`AVATAR_DIR` 与 admin GridFS 未删除；新 S3 不迁移旧字节。
- 生产问题（启动失败、OOM、SELinux 等）：见 [`../native/README.md`](../native/README.md) 第 8 节排障表。
