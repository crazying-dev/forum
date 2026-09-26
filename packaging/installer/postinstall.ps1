# Forum client - post install tasks (ASCII source on purpose:
# PowerShell 5.1 reads BOM-less .ps1 as ANSI, so every Chinese string
# below is built from [char] code points instead of being typed directly.)
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$AppDir,
    [string]$Version = '1.0.0',
    [switch]$NoStartMenu,
    [switch]$DesktopShortcut
)

$ErrorActionPreference = 'Continue'

# Forum client
$AppName = -join ([char]0x5996, [char]0x7CBE, [char]0x8BBA, [char]0x575B, [char]0x5BA2, [char]0x6237, [char]0x7AEF)
# URL:Forum protocol
$ProtoDesc = 'URL:' + $AppName + ' protocol'
$Publisher = 'CrForum'

Write-Host "  app name : $AppName"

# ---------------------------------------------------------------- uninstall
$uninstall = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CrForum'
New-Item -Path $uninstall -Force | Out-Null
Set-ItemProperty -Path $uninstall -Name 'DisplayName'     -Value $AppName
Set-ItemProperty -Path $uninstall -Name 'DisplayVersion'  -Value $Version
Set-ItemProperty -Path $uninstall -Name 'Publisher'       -Value $Publisher
Set-ItemProperty -Path $uninstall -Name 'DisplayIcon'     -Value ("$Exe,0")
Set-ItemProperty -Path $uninstall -Name 'InstallLocation' -Value $AppDir
Set-ItemProperty -Path $uninstall -Name 'UninstallString' -Value ('"' + (Join-Path $AppDir 'uninstall.cmd') + '"')
Set-ItemProperty -Path $uninstall -Name 'QuietUninstallString' -Value ('"' + (Join-Path $AppDir 'uninstall.cmd') + '" /quiet')
Set-ItemProperty -Path $uninstall -Name 'NoModify' -Value 1 -Type DWord
Set-ItemProperty -Path $uninstall -Name 'NoRepair' -Value 1 -Type DWord
Write-Host '  [ok] uninstall entry'

# ------------------------------------------------------------ URI scheme
$proto = 'HKCU:\Software\Classes\Crforum'
New-Item -Path $proto -Force | Out-Null
Set-Item -Path $proto -Value $ProtoDesc
New-ItemProperty -Path $proto -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
New-Item -Path "$proto\DefaultIcon" -Force | Out-Null
Set-Item -Path "$proto\DefaultIcon" -Value ("$Exe,0")
New-Item -Path "$proto\shell\open\command" -Force | Out-Null
Set-Item -Path "$proto\shell\open\command" -Value ('"' + $Exe + '" "%1"')
Write-Host '  [ok] Crforum:// handler'

# ------------------------------------------------------------- shortcuts
function New-Shortcut([string]$Path, [string]$Target, [string]$WorkDir) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($Path)
        $link.TargetPath = $Target
        $link.WorkingDirectory = $WorkDir
        $link.IconLocation = "$Target,0"
        $link.Description = $AppName
        $link.Save()
        return $true
    }
    catch { return $false }
}

if (-not $NoStartMenu) {
    $programs = [Environment]::GetFolderPath('Programs')
    if ($programs) {
        $lnk = Join-Path $programs ($AppName + '.lnk')
        if (New-Shortcut -Path $lnk -Target $Exe -WorkDir $AppDir) { Write-Host "  [ok] start menu: $lnk" }
    }
}
if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop) {
        $lnk = Join-Path $desktop ($AppName + '.lnk')
        if (New-Shortcut -Path $lnk -Target $Exe -WorkDir $AppDir) { Write-Host "  [ok] desktop: $lnk" }
    }
}

Write-Host '  [ok] post install done'
exit 0
