# 打包说明

本目录存放 Windows 客户端的全部打包配置。

## 一键打包

```powershell
# 主后端：Nuitka（默认，产物包含大量 .pyd/.dll，目录里没有 .pyc）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1

# 首次打包前装依赖
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -InstallDeps

# 备用后端：PyInstaller onedir（同样不使用单文件）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Backend pyinstaller

# 只要 dist，不出安装包
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipInstaller
```

## 产物

| 路径 | 说明 |
|------|------|
| `packaging\output\forum.dist\` | 客户端目录（`forum.exe` + 依赖 DLL + `resources/`） |
| `packaging\output\forum_setup.exe` | 自解压安装包（iexpress，含 `install.cmd`） |
| `packaging\installer\output\` | Inno Setup 安装包（装了 ISCC 时生成） |

`packaging\output\` 已在 `.gitignore` 中排除，不会入库。

## 目录结构

```
packaging/
  build.ps1              打包主脚本（仅 ASCII，避免 PowerShell 5.1 编码问题）
  forum.spec             PyInstaller 备用配置（onedir / 收集 live2d / 不启用 UPX）
  version.json          版本与产品信息（UTF-8，脚本显式按 UTF-8 读取）
  version_info.txt       PyInstaller 的 Windows 版本资源
  installer/
    install.cmd          自解压安装包的入口（复制 + 写注册表 + 启动）
    postinstall.ps1      注册卸载项 / Crforum:// 协议 / 开始菜单快捷方式
    uninstall.cmd        卸载（默认保留 ~/.Cr/forum 用户数据，/purge 才删）
    CrForum.iss          Inno Setup 脚本（可选，优先于 iexpress）
    README.txt           随安装包分发的说明
```

## 设计要点

1. **不是单文件**：产物是一个目录（`forum.dist`），exe 旁就是依赖，启动更快、杀软误报更少。
2. **产物多 DLL**：Nuitka `--standalone` 把每个模块编译成 `.pyd`，第三方原生库（Qt / live2d-py / numpy）以 `.dll` 形式存在，**不会生成 `.pyc`**；构建时脚本会打印 dll/pyd 与 pyc 数量供核对。
3. **资源打包**：`--include-data-dir=resources=resources`，因此 `forum.dist/resources/` 包含图标、鼠标指针帧、WIKI 图片。
4. **安装包写入注册表**：
   - `HKCU\Software\Classes\Crforum`（`URL Protocol`）→ 支持 `Crforum://post/PS...` 唤起客户端
   - `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\CrForum` → 卸载入口
   - 全程只用 HKCU，**不需要管理员权限**
5. **自动更新**：客户端内置更新器按 `app/constants.py` 里混淆过的地址下载新版 exe，由 `~/.Cr/forum/update/apply_update.cmd` 在主程序退出后替换并重启。
6. **编码**：PowerShell 5.1 会把无 BOM 的 `.ps1` 当 ANSI 读，因此 `build.ps1` / `postinstall.ps1` 一律只用 ASCII；需要中文（如快捷方式名）时用 `[char]0x....` 拼出来；`version.json` 显式按 UTF-8 读取。

## 清理

```powershell
Remove-Item -Recurse -Force packaging\output
```
