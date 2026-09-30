<#
  forum-Android  |  Android build-environment bootstrap for Windows
  -----------------------------------------------------------------
  Every step is idempotent: pieces that already exist are skipped.

    1) Locate or install a JDK 17 (Microsoft Build of OpenJDK 17 via winget)
    2) Download and unpack the official Android SDK command-line tools
    3) Accept SDK licenses and install:
         platform-tools, platforms;android-36, build-tools;36.0.0
    4) Write local.properties (sdk.dir=...) so Gradle/AGP can find the SDK
    5) Persist JAVA_HOME / ANDROID_HOME for the current user

  Usage (from anywhere):
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup-android-env.ps1

  Switches:
    -SdkRoot <path>   SDK location            (default: %LOCALAPPDATA%\Android\Sdk)
    -JdkHome <path>   Use an existing JDK 17  (skips winget)
    -SkipJdk          Skip the JDK step
    -SkipSdk          Skip the SDK steps
    -NoPersistEnv     Do not write user environment variables

  Then build with:
    .\gradlew.bat assembleDebug

  Total SDK download is roughly 500 MB. dl.google.com must be reachable.
#>

[CmdletBinding()]
param(
    [string]$SdkRoot = (Join-Path $env:LOCALAPPDATA 'Android\Sdk'),
    [string]$JdkHome = '',
    [switch]$SkipJdk,
    [switch]$SkipSdk,
    [switch]$NoPersistEnv
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$nl = [Environment]::NewLine

# commandlinetools-win-<build>_latest.zip ; build 16111833 was published 2026-08-19
$CmdlineToolsBuild = '16111833'
$CmdlineToolsUrl = 'https://dl.google.com/android/repository/commandlinetools-win-' + $CmdlineToolsBuild + '_latest.zip'
$SdkPackages = @('platform-tools', 'platforms;android-36', 'build-tools;36.0.0')
$JdkDownloadPage = 'https://learn.microsoft.com/java/openjdk/download'

function Write-Step([string]$m) { Write-Host '' ; Write-Host ('=== ' + $m + ' ===') -ForegroundColor Cyan }
function Write-Ok([string]$m)   { Write-Host ('  [ OK ] ' + $m) -ForegroundColor Green }
function Write-Skip([string]$m) { Write-Host ('  [SKIP] ' + $m) -ForegroundColor DarkGray }
function Write-Warn2([string]$m){ Write-Host ('  [WARN] ' + $m) -ForegroundColor Yellow }
function Write-Info([string]$m) { Write-Host ('  [ .. ] ' + $m) -ForegroundColor Gray }

function Test-Jdk17([string]$home) {
    if ([string]::IsNullOrWhiteSpace($home)) { return $false }
    $java = Join-Path $home 'bin\java.exe'
    if (-not (Test-Path $java)) { return $false }
    try {
        $raw = (& $java '-version' 2>&1 | Out-String)
        return ($raw -match 'version .17\.')
    } catch {
        return $false
    }
}

function Find-Jdk17 {
    $candidates = New-Object System.Collections.ArrayList
    if ($env:JAVA_HOME) { [void]$candidates.Add($env:JAVA_HOME) }
    $pf   = $env:ProgramFiles
    $pf86 = ${env:ProgramFiles(x86)}
    $roots = @()
    if ($pf)   { $roots += (Join-Path $pf 'Microsoft\jdk-17*') }
    if ($pf)   { $roots += (Join-Path $pf 'Eclipse Adoptium\jdk-17*') }
    if ($pf)   { $roots += (Join-Path $pf 'Java\jdk-17*') }
    if ($pf)   { $roots += (Join-Path $pf 'Amazon Corretto\jdk17*') }
    if ($pf)   { $roots += (Join-Path $pf 'Zulu\zulu-17*') }
    if ($pf)   { $roots += (Join-Path $pf 'Android\Android Studio\jbr') }
    if ($pf86) { $roots += (Join-Path $pf86 'Java\jdk-17*') }
    foreach ($g in $roots) {
        Get-ChildItem -Path $g -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { [void]$candidates.Add($_.FullName) }
    }
    foreach ($c in $candidates) {
        if (Test-Jdk17 $c) { return $c }
    }
    return ''
}

Write-Host ''
Write-Host '**********************************************************' -ForegroundColor DarkCyan
Write-Host '*  forum-Android  build environment bootstrap (Windows)   *' -ForegroundColor DarkCyan
Write-Host '**********************************************************' -ForegroundColor DarkCyan
Write-Host ('  SDK root : ' + $SdkRoot)
Write-Host ('  Work dir : ' + (Get-Location).Path)

# ---------------- 1) JDK 17 ----------------
Write-Step 'Step 1/5  JDK 17'
if ($SkipJdk) {
    Write-Skip 'JDK step skipped (-SkipJdk)'
} else {
    if ((-not [string]::IsNullOrWhiteSpace($JdkHome)) -and (Test-Jdk17 $JdkHome)) {
        Write-Ok ('Using -JdkHome : ' + $JdkHome)
    } else {
        $found = Find-Jdk17
        if ($found) {
            $JdkHome = $found
            Write-Ok ('Found JDK 17 : ' + $JdkHome)
        } else {
            $wingetCmd = (Get-Command winget -ErrorAction SilentlyContinue)
            if (-not $wingetCmd) {
                Write-Warn2 'winget not found. Install JDK 17 manually, then re-run with -JdkHome <path>:'
                Write-Host ('          ' + $JdkDownloadPage) -ForegroundColor Yellow
                exit 2
            }
            Write-Info 'Installing Microsoft.OpenJDK.17 via winget (this may take a few minutes)...'
            & $wingetCmd.Source install -e --id Microsoft.OpenJDK.17 --accept-source-agreements --accept-package-agreements --disable-interactivity
            $found = Find-Jdk17
            if ($found) {
                $JdkHome = $found
                Write-Ok ('Installed JDK 17 : ' + $JdkHome)
            } else {
                Write-Warn2 'winget finished but no JDK 17 was detected. Re-run with -JdkHome <path>.'
                Write-Host ('          ' + $JdkDownloadPage) -ForegroundColor Yellow
                exit 2
            }
        }
    }
    $env:JAVA_HOME = $JdkHome
    Write-Ok ('JAVA_HOME (this session) = ' + $env:JAVA_HOME)
}

# ---------------- 2) command-line tools ----------------
if ($SkipSdk) {
    Write-Step 'Step 2-4/5  Android SDK skipped (-SkipSdk)'
} else {
    Write-Step 'Step 2/5  Android SDK command-line tools'
    $sdkManager = Join-Path $SdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'
    if (Test-Path $sdkManager) {
        Write-Skip ('sdkmanager already present : ' + $sdkManager)
    } else {
        Write-Info ('Downloading ' + $CmdlineToolsUrl)
        Write-Info '(about 155 MB - please wait)'
        $tmpZip = Join-Path $env:TEMP ('cmdline-tools-' + $CmdlineToolsBuild + '.zip')
        $tmpDir = Join-Path $env:TEMP ('cmdline-tools-' + $CmdlineToolsBuild)
        if (Test-Path $tmpZip) {
            Write-Skip 'zip already downloaded'
        } else {
            Invoke-WebRequest -Uri $CmdlineToolsUrl -OutFile $tmpZip -UseBasicParsing
        }
        if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
        Write-Info 'Extracting...'
        Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
        $inner = Join-Path $tmpDir 'cmdline-tools'
        if (-not (Test-Path $inner)) { throw ('Unexpected archive layout: ' + $inner + ' not found') }
        $destParent = Join-Path $SdkRoot 'cmdline-tools'
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        $destLatest = Join-Path $destParent 'latest'
        if (Test-Path $destLatest) { Remove-Item $destLatest -Recurse -Force }
        Move-Item -Path $inner -Destination $destLatest
        Write-Ok ('Installed cmdline-tools to ' + $destLatest)
    }

    Write-Step 'Step 3/5  Accept licenses and install SDK packages'
    if (-not (Test-Path $sdkManager)) { throw ('sdkmanager still missing: ' + $sdkManager) }
    $yes = (1..80 | ForEach-Object { 'y' }) -join $nl
    Write-Info 'Accepting SDK licenses...'
    try {
        $yes | & $sdkManager ('--sdk_root=' + $SdkRoot) --licenses | Out-Null
    } catch {
        Write-Warn2 ('license step reported: ' + $_.Exception.Message)
    }
    Write-Info ('Installing: ' + ($SdkPackages -join ', '))
 $yes | & $sdkManager ('--sdk_root=' + $SdkRoot) @SdkPackages

    $missing = @()
    if (-not (Test-Path (Join-Path $SdkRoot 'platform-tools\adb.exe'))) { $missing += 'platform-tools' }
    if (-not (Test-Path (Join-Path $SdkRoot 'platforms\android-36\android.jar'))) { $missing += 'platforms;android-36' }
    if (-not (Test-Path (Join-Path $SdkRoot 'build-tools\36.0.0\aapt2.exe'))) { $missing += 'build-tools;36.0.0' }
    if ($missing.Count -gt 0) {
        Write-Warn2 ('These packages look incomplete: ' + ($missing -join ', '))
        Write-Warn2 'Re-run this script (it is idempotent), or install them via Android Studio.'
    } else {
        Write-Ok 'All SDK packages are in place.'
    }

    Write-Step 'Step 4/5  Write local.properties'
    $repoRoot = (Get-Location).Path
    if (-not (Test-Path (Join-Path $repoRoot 'settings.gradle.kts'))) {
        $parentDir = Split-Path $repoRoot -Parent
        if ($parentDir -and (Test-Path (Join-Path $parentDir 'settings.gradle.kts'))) { $repoRoot = $parentDir }
    }
    $lp = Join-Path $repoRoot 'local.properties'
    $sdkForward = $SdkRoot.Replace('\', '/')
    $lpContent = '# Generated by tools/setup-android-env.ps1 - git-ignored, do not commit.' + $nl + 'sdk.dir=' + $sdkForward + $nl
    Set-Content -Path $lp -Value $lpContent -Encoding ASCII
    Write-Ok ('Wrote ' + $lp)
    $env:ANDROID_HOME = $SdkRoot
    $env:ANDROID_SDK_ROOT = $SdkRoot
}

# ---------------- 5) persist ----------------
Write-Step 'Step 5/5  Environment variables'
if ($NoPersistEnv) {
    Write-Skip 'Persistence skipped (-NoPersistEnv)'
} else {
    if ($JdkHome) {
        [Environment]::SetEnvironmentVariable('JAVA_HOME', $JdkHome, 'User')
        Write-Ok ('JAVA_HOME    -> ' + $JdkHome + '  (user scope)')
    }
    if (-not $SkipSdk) {
        [Environment]::SetEnvironmentVariable('ANDROID_HOME', $SdkRoot, 'User')
        [Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $SdkRoot, 'User')
        Write-Ok ('ANDROID_HOME -> ' + $SdkRoot + '  (user scope)')
    }
}

Write-Host ''
Write-Host '----------------------------------------------------------' -ForegroundColor DarkCyan
Write-Host ' Done. Next steps:' -ForegroundColor Cyan
Write-Host '   1. Close this terminal and open a NEW one.'
Write-Host '   2. cd into the repository root (where gradlew.bat lives).'
Write-Host '   3. .\gradlew.bat assembleDebug'
Write-Host '      APK -> app\build\outputs\apk\debug\app-debug.apk'
Write-Host ''
Write-Host '   The first build downloads Gradle 8.14.5 (~138 MB) into %USERPROFILE%\.gradle.'
Write-Host '   Install on a device with:'
Write-Host '     adb install -r app\build\outputs\apk\debug\app-debug.apk'
Write-Host '----------------------------------------------------------' -ForegroundColor DarkCyan
Write-Host ''
