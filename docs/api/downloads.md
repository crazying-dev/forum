# 下载客户端 / 版本检查

数据源：GitHub Releases `yoyo-ouo/yj-forum-ouo`（服务端 10 分钟缓存，可选 `GITHUB_TOKEN`）。GitHub 读不到时：`/downloads/*` 返回 502；`/api/app/releases` 与版本闸门返回空清单（无平台、无 min_versions，不展示发布、不强制升级）。不回退内置清单。

## 列表

`GET /ov2/api/downloads/releases?page=1&page_size=20&platform=windows`

条目：`{platform,version,channel,date,size,url,filename,sha256,notes,mandatory}`。

## 最新版

`GET /ov2/api/downloads/latest?platform=windows` → `{success,item}`。

## 版本检查

`GET /ov2/api/downloads/check?platform=windows&version=1.3.17`
```json
{ "success":true, "available":true, "mandatory":false, "current":"1.3.17", "latest":"1.3.18", "min_version":"1.3.18", "release":{...}, "download_url":"..." }
```

`min_versions` 约定：每个平台最新 stable Release 的版本；低于该版本旧 APP 的 `/api/*` 请求返回 426。

## 镜像

`GET /ov2/api/downloads/mirror/:platform/:filename`：仅允许清单中的 GitHub 资产；支持 Range/206；host 白名单 `github.com/githubusercontent.com/githubassets.com`。
