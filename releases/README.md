# 客户端安装包目录（releases/）

本目录用于存放客户端安装包（例如 `forum.exe`），由后端只读接口
`/api/app/windows/forum.exe` 对外分发（客户端常量 `UPDATE_EXE_URL` 指向它）。

- **安装包本体不入库**：`.gitignore` 忽略了 `releases/*`，仅跟踪本说明与 `.gitkeep` 占位文件。
- 部署时把发行包放进本目录（也可用环境变量 `APP_RELEASE_DIR` 指定其它路径）；
  文件名必须与 `app_releases.json` 中对应 `releases[].url` 的末段一致（当前为 `forum.exe`）。
- 版本号、发布时间、体积、更新说明等元数据统一在仓库根目录的 `app_releases.json` 维护；
  后端只读该文件，按「文件 mtime + 大小」自动刷新缓存，改完无需重启服务。
- 安装包缺失时接口返回 503 + JSON 提示（不会 500），客户端可据此提示用户稍后再试。
