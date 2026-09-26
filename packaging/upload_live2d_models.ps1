# ============================================================
#  Upload the Live2D model packages used by the version switcher
#  to the production server's  static/live2d/  directory.
#
#  The server repository already tracks  static/live2d/HEI.lpk ,
#  so the *preferred* upload channel is a normal git commit + push
#  plus a on the server.  This script is the fallback for when
#  you would rather copy the files straight over SSH and keep the
#  binaries out of git history.
#
#  Usage
#    powershell -ExecutionPolicy Bypass -File packaging/upload_live2d_models.ps1 -DryRun
#    powershell -ExecutionPolicy Bypass -File packaging/upload_live2d_models.ps1 `
#        -Server root@154.219.110.63 `
#        -RemoteDir /root/forum/static/live2d
#
#  Optional
#    -SourceDir D:\models   staging directory (default: <repo>\assets\live2d)
#    -DryRun                only print what would be sent
#
#  Requires an OpenSSH client (scp) on PATH plus a usable SSH key,
#  agent or interactive password prompt.  ASCII only on purpose.
# ============================================================

param(
    [string]$Server    = "root@154.219.110.63",
    [string]$RemoteDir = "/root/forum/static/live2d",
    [string]$SourceDir = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Local name -> remote name hosted by the server.
# 4.0 keeps the historical HEI.lpk name as well, see app/constants.py.
$Files = @(
    @("HEI1.1.lpk",   "HEI11.lpk"),
    @("HEI2.3.lpk",   "HEI23.lpk"),
    @("HEI3.0.1.lpk", "HEI301.lpk"),
    @("HEI3.0.2.lpk", "HEI302.lpk"),
    @("HEI4.0.lpk",   "HEI40.lpk")
)

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path (Split-Path -Parent $PSScriptRoot) "assets\live2d"
}

if (-not (Test-Path -LiteralPath $SourceDir)) {
    Write-Host "[!] source directory not found: $SourceDir"
    Write-Host "    pass -SourceDir <dir> pointing at the folder holding the .lpk files."
    exit 2
}

$scp = Get-Command scp -ErrorAction SilentlyContinue
if (-not $scp -and -not $DryRun) {
    Write-Host "[!] scp was not found on PATH. Install the OpenSSH client"
    Write-Host "    (Settings > Apps > Optional features > OpenSSH Client) and retry."
    exit 3
}

Write-Host "server   : $Server"
Write-Host "remote   : $RemoteDir/"
Write-Host "source   : $SourceDir"
Write-Host ""

$missing = @()
foreach ($pair in $Files) {
    $local = Join-Path $SourceDir $pair[0]
    if (-not (Test-Path -LiteralPath $local)) { $missing += $local }
}
if ($missing.Count -gt 0) {
    Write-Host "[!] missing local files:"
    foreach ($m in $missing) { Write-Host "    $m" }
    exit 4
}

foreach ($pair in $Files) {
    $local  = Join-Path $SourceDir $pair[0]
    $remote = "$Server`:$RemoteDir/$($pair[1])"
    $size   = (Get-Item -LiteralPath $local).Length
    Write-Host ("upload: {0}  ({1:n0} bytes)  ->  {2}" -f $pair[0], $size, $pair[1])
    if ($DryRun) { continue }
    & scp -C "$local" "$remote"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] scp failed for $($pair[0]) (exit $LASTEXITCODE)"
        exit 5
    }
}

Write-Host ""
if ($DryRun) {
    Write-Host "dry run complete - nothing was transferred."
} else {
    Write-Host "done. verify with:  curl -I https://www.yjlt.top/static/live2d/HEI40.lpk"
}
