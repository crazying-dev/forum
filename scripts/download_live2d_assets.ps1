# Live2D 资源下载脚本（Windows PowerShell 版）
# 用途：将 HEI.lpk / Live2DLPK.js / 5 张 GIF / 2 张 WIKI 封面 下载到本地 static/ 目录，
#       使前端走同站路径 /static/...（CDN 仅作兜底）。
# 用法：powershell -ExecutionPolicy Bypass -File scripts/download_live2d_assets.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Base = "https://assets.crazying-dev.top/text/one"

# 目标目录
$Dirs = @{
    "Live2D"   = Join-Path $Root "static\live2d"
    "Live2DJS" = Join-Path $Root "static\live2d\js"
    "GIF"      = Join-Path $Root "static\live2d\gif"
    "WIKI"     = Join-Path $Root "static\img\wiki"
}
foreach ($k in $Dirs.Keys) { New-Item -ItemType Directory -Force -Path $Dirs[$k] | Out-Null }

# 下载清单: [远程相对路径, 本地完整路径]
$Files = @(
    @("Live2D/HEI.lpk",                        (Join-Path $Dirs["Live2D"] "HEI.lpk")),
    @("JS/Live2DLPK.js",                       (Join-Path $Dirs["Live2DJS"] "Live2DLPK.js")),
    @("Live2D/gif/待机.gif",                   (Join-Path $Dirs["GIF"] "待机.gif")),
    @("Live2D/gif/跳舞.gif",                   (Join-Path $Dirs["GIF"] "跳舞.gif")),
    @("Live2D/gif/摸头.gif",                   (Join-Path $Dirs["GIF"] "摸头.gif")),
    @("Live2D/gif/生气.gif",                   (Join-Path $Dirs["GIF"] "生气.gif")),
    @("Live2D/gif/高兴.gif",                   (Join-Path $Dirs["GIF"] "高兴.gif")),
    @("Live2D/guanfang_cover.webp",            (Join-Path $Dirs["WIKI"] "guanfang_cover.webp")),
    @("Live2D/personal_cover.jpg",             (Join-Path $Dirs["WIKI"] "personal_cover.jpg"))
)

foreach ($f in $Files) {
    $url = "$Base/$($f[0])"
    $dest = $f[1]
    Write-Host "下载: $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-Host "  完成: $dest"
    }
    catch {
        Write-Warning "  失败: $url ($($_.Exception.Message))"
    }
}

Write-Host ""
Write-Host "下载结束。若个别文件失败，请检查网络后重新运行本脚本。"
