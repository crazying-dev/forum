#Requires -Version 5.1
<#
.SYNOPSIS
    Forum Windows client - build script (ASCII only: PowerShell 5.1 reads
    BOM-less .ps1 as ANSI, so Chinese text must not live in this file).
.DESCRIPTION
    Backend: nuitka (default) - standalone, many .pyd/.dll, no .pyc
    Backend: pyinstaller      - onedir, non-onefile fallback
    Optionally builds a self-extracting installer with iexpress.exe,
    or with Inno Setup (ISCC.exe) when it is installed.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Backend pyinstaller -InstallDeps
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipInstaller -SkipTests
#>
[CmdletBinding()]
param(
    [ValidateSet('nuitka', 'pyinstaller')]
    [string]$Backend = 'nuitka',

    [switch]$InstallDeps,
    [switch]$SkipInstaller,
    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$KeepIntermediate,

    [string]$Version = '',
    [string]$Python = '',

    # Extra flags forwarded to Nuitka, e.g. @('--nofollow-import-to=tkinter')
    [string[]]$NuitkaExtra = @()
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$OutputDir = Join-Path $ScriptDir 'output'
$InstallerDir = Join-Path $ScriptDir 'installer'

# Product identity comes from version.json, read explicitly as UTF-8.
$MetaPath = Join-Path $ScriptDir 'version.json'
$Meta = @{}
if (Test-Path $MetaPath) {
    $raw = [System.IO.File]::ReadAllText($MetaPath, [System.Text.Encoding]::UTF8)
    $Meta = $raw | ConvertFrom-Json
}
if (-not $Version) {
    if ($Meta.version) { $Version = [string]$Meta.version } else { $Version = '1.0.0' }
}
$ProductName = "Forum Client"
$FileDesc = "Forum Windows Client"
$Copyright = "(c) 2026 Forum"

function Write-Step([string]$Text) { Write-Host "`n==== $Text ====" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "  [ok] $Text" -ForegroundColor Green }
function Write-Warn2([string]$Text) { Write-Host "  [!!] $Text" -ForegroundColor Yellow }

function Resolve-Python([string]$Explicit) {
    if ($Explicit) { return $Explicit }
    foreach ($candidate in @('python', 'python3', 'py')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw 'Python not found. Pass -Python <path>'
}

Write-Step 'Environment'
$Python = Resolve-Python $Python
Write-Ok "Python      : $Python"
$pyVersion = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Ok "Version     : $pyVersion  (target 3.12+)"
Write-Ok "Build ver   : $Version"
Set-Location $Root
Write-Ok "Project root: $Root"

# ---------------------------------------------------------------- deps
if ($InstallDeps) {
    Write-Step 'Install dependencies'
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $Root 'requirements.txt')
    if ($Backend -eq 'nuitka') {
        & $Python -m pip install 'nuitka>=2.8.4'
    } else {
        & $Python -m pip install 'pyinstaller>=6.20' 'pyinstaller-hooks-contrib'
    }
}

# ------------------------------------------------------------ resources
Write-Step 'Resource check'
$required = @(
    'resources\icon\icon.ico',
    'resources\icon\logo.png',
    'resources\img\favicon.png',
    'resources\cursors\manifest.json'
)
$missing = @()
foreach ($item in $required) {
    if (Test-Path (Join-Path $Root $item)) { Write-Ok $item } else { $missing += $item; Write-Warn2 "missing: $item" }
}
if ($missing.Count -gt 0) { Write-Warn2 'resources/ is incomplete; the build output may be broken' }

# ---------------------------------------------------------------- tests
if (-not $SkipTests) {
    Write-Step 'Unit tests'
    $runner = Join-Path $Root 'tests\run_tests.py'
    if (Test-Path $runner) {
        & $Python $runner
        if ($LASTEXITCODE -ne 0) { throw "tests failed (exit=$LASTEXITCODE)" }
        Write-Ok 'tests passed'
    } else {
        Write-Warn2 'tests\run_tests.py not found - skipped'
    }
}

# ---------------------------------------------------------------- build
if (Test-Path $OutputDir) { Remove-Item -Recurse -Force $OutputDir }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$DistDir = Join-Path $OutputDir 'forum.dist'

if (-not $SkipBuild) {
    if ($Backend -eq 'nuitka') {
        Write-Step 'Nuitka standalone build'
        $cli = @(
            '-m', 'nuitka',
            '--standalone',
            '--enable-plugin=pyqt6',
            '--windows-console-mode=disable',
            "--windows-icon-from-ico=$Root\resources\icon\icon.ico",
            "--include-data-dir=$Root\resources=resources",
            '--include-package=live2d',
            '--include-package-data=live2d',
            '--assume-yes-for-downloads',
            "--output-dir=$OutputDir",
            '--output-filename=forum.exe',
            '--company-name=CrForum',
            "--product-name=$ProductName",
            "--file-description=$FileDesc",
            "--file-version=$Version",
            "--product-version=$Version",
            "--copyright=$Copyright"
        )
        if (-not $KeepIntermediate) { $cli += '--remove-output' }
        if ($NuitkaExtra.Count -gt 0) { $cli += $NuitkaExtra }
        $cli += (Join-Path $Root 'main.py')
        & $Python @cli
        if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed (exit=$LASTEXITCODE)" }
        $built = Join-Path $OutputDir 'main.dist'
        if (Test-Path $built) { Move-Item $built $DistDir }
    }
    else {
        Write-Step 'PyInstaller onedir build'
        $cli = @(
            '-m', 'PyInstaller',
            '--noconfirm', '--clean',
            "--distpath=$OutputDir",
            "--workpath=$(Join-Path $OutputDir '.pyinstaller')",
            (Join-Path $ScriptDir 'forum.spec')
        )
        & $Python @cli
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit=$LASTEXITCODE)" }
        $built = Join-Path $OutputDir 'forum'
        if (Test-Path $built) { Move-Item $built $DistDir }
    }
    Write-Ok "dist: $DistDir"
}

if (-not (Test-Path (Join-Path $DistDir 'forum.exe'))) {
    throw "forum.exe not found - build failed: $DistDir"
}

$size = (Get-ChildItem $DistDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
$dllCount = (Get-ChildItem $DistDir -Recurse -Include *.dll, *.pyd | Measure-Object).Count
$pycCount = (Get-ChildItem $DistDir -Recurse -Include *.pyc | Measure-Object).Count
Write-Ok ("dist size   : {0:N1} MB" -f ($size / 1MB))
Write-Ok "dll/pyd     : $dllCount"
Write-Ok "pyc files   : $pycCount"

# ------------------------------------------------------------ installer
if (-not $SkipInstaller) {
    Write-Step 'Build installer'
    $stage = Join-Path $OutputDir 'installer_stage'
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Path (Join-Path $stage 'payload') | Out-Null
    Copy-Item -Recurse -Force (Join-Path $DistDir '*') (Join-Path $stage 'payload')
    foreach ($f in @('install.cmd', 'uninstall.cmd', 'postinstall.ps1', 'README.txt')) {
        $src = Join-Path $InstallerDir $f
        if (Test-Path $src) { Copy-Item -Force $src $stage }
    }

    $iscc = $null
    foreach ($p in @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe',
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )) {
        if (Test-Path $p) { $iscc = $p; break }
    }
    if ($iscc) {
        Write-Ok "Inno Setup : $iscc"
        & $iscc "/DMyAppVersion=$Version" "/DStageDir=$stage" (Join-Path $InstallerDir 'CrForum.iss')
        if ($LASTEXITCODE -eq 0) { Write-Ok "installer written to $InstallerDir\output" }
        else { Write-Warn2 "Inno Setup failed (exit=$LASTEXITCODE) - falling back to iexpress"; $iscc = $null }
    }

    if (-not $iscc) {
        $iexpress = Join-Path $env:SystemRoot 'System32\iexpress.exe'
        if (-not (Test-Path $iexpress)) {
            Write-Warn2 'iexpress.exe not present - skipping installer (ship forum.dist as-is)'
        }
        else {
            Write-Ok 'Generating self-extracting installer with iexpress.exe'
            $target = Join-Path $OutputDir 'forum_setup.exe'
            $listLines = @()
            $stringLines = @()
            $i = 0
            foreach ($file in (Get-ChildItem $stage -Recurse -File)) {
                $rel = $file.FullName.Substring($stage.Length + 1)
                $var = "FILE$i"
                $listLines += "%$var%="
                $stringLines += "$var=$rel"
                $i++
            }
            $sed = @()
            $sed += '[Version]'
            $sed += 'Class=IEXPRESS'
            $sed += 'SEDVersion=3'
            $sed += '[Options]'
            $sed += 'PackagePurpose=InstallApp'
            $sed += 'ShowInstallProgramWindow=1'
            $sed += 'HideExtractAnimation=0'
            $sed += 'UseLongFileName=1'
            $sed += 'InsideCompressed=0'
            $sed += 'CAB_FixedSize=0'
            $sed += 'CAB_ResvCodeSigning=0'
            $sed += 'RebootMode=N'
            $sed += 'InstallPrompt='
            $sed += 'DisplayLicense='
            $sed += 'FinishMessage=CrForum client installed.'
            $sed += "TargetName=$target"
            $sed += 'FriendlyName=CrForum Client Setup'
            $sed += 'AppLaunched=install.cmd'
            $sed += 'PostInstallCmd=<None>'
            $sed += 'AdminQuietInstCmd='
            $sed += 'UserQuietInstCmd='
            $sed += 'SourceFiles=SourceFiles'
            $sed += '[SourceFiles]'
            $sed += "SourceFiles0=$stage"
            $sed += '[SourceFiles0]'
            $sed += $listLines
            $sed += '[Strings]'
            $sed += $stringLines
            $sedPath = Join-Path $OutputDir 'crforum.sed'
            Set-Content -Path $sedPath -Value ($sed -join "`r`n") -Encoding ASCII
            & $iexpress /N /Q $sedPath
            if (Test-Path $target) { Write-Ok "installer  : $target" }
            else { Write-Warn2 'iexpress produced nothing - ship forum.dist as-is' }
        }
    }
}

Write-Step 'Done'
Write-Host "  backend   : $Backend"
Write-Host "  dist dir  : $DistDir"
Write-Host "  exe       : $(Join-Path $DistDir 'forum.exe')"
