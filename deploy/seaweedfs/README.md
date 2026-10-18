# SeaweedFS（S3）部署与使用

> 本目录是单机 SeaweedFS 的开发/单机生产参考。S3 只监听 `127.0.0.1:8333`，前端统一经 ouo `/ov2/api/media/<id>` 代理取流；admin 前端也经 ouo 取图。

## 1. 启动

```bash
cd yj-forum-ouo/deploy/seaweedfs
cp s3.json.example s3.json   # 首次：改成强随机 access/secret
mkdir -p data
docker compose up -d
```

或在仓库根：

```bash
make s3-up      # 自动确保容器/数据目录/bucket
make s3-status
make s3-logs
make s3-down
```

## 2. 配置 ouo / admin

在 `yj-forum-ouo/server/.env` 与 `yj-forum-admin/server/.env` 中设置同一组值：

```env
S3_ENABLED=true
S3_ENDPOINT=http://127.0.0.1:8333
S3_REGION=us-east-1
S3_BUCKET=yj-forum
S3_ACCESS_KEY=<s3.json 中的 accessKey>
S3_SECRET_KEY=<s3.json 中的 secretKey>
S3_USE_PATH_STYLE=true
```

> 建议 ouo 与 admin 使用不同的 key（`s3.json.example` 已给出两个 identity），权限都只到 `yj-forum` bucket。

## 3. Bucket / object key

- 单 bucket：`yj-forum`。
- 前缀：`posts/`、`comments/`、`world/`、`chat/`、`guilds/{uuid}/`、`guides/`、`avatars/`、`feedback/`。
- 私有 bucket；应用 key 不授予 `List` 以外的全局权限；不要对公网开放 8333。

## 4. 备份 / 恢复

- 数据目录：`deploy/seaweedfs/data`（生产建议挂到独立磁盘）。
- 停止写入后快照整个数据目录；恢复时停容器、还原目录、再启动。
- 定期执行 `weed shell` 的 `volume.check.disk` / `volume.fsck`（按 SeaweedFS 版本命令为准）。
- 备份同时覆盖 PG 与 admin GridFS（旧资源仍可能被读取）。

## 5. 故障排查

- `docker logs ouo-seaweedfs` 看 S3 gateway 日志。
- `curl -i http://127.0.0.1:8333/` 返回 403 说明网关在跑（未签名请求被拒是正常的）。
- 上传 500：先确认 bucket 已创建、key 有 `Write:yj-forum` 权限、`S3_ENDPOINT` 可从服务容器/主机访问。
- 旧资源 404：确认 `MEDIA_DIR`/`AVATAR_DIR` 与 admin GridFS 未删除；新 S3 不迁移旧字节。
