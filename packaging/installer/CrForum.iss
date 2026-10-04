; ============================================================
; Inno Setup script for the Forum Windows client (optional path).
; build.ps1 uses this automatically when ISCC.exe is installed.
; Compile manually:
;   ISCC.exe /DMyAppVersion=1.3.16 /DStageDir=..\output\installer_stage CrForum.iss
; ============================================================

#define MyAppName "Forum Client"
#define MyAppExeName "forum.exe"

#ifndef MyAppVersion
  #define MyAppVersion "1.3.16"
#endif
; 安装包自身的文件信息（四段式版本号，便于在文件属性里看到版本）
#define MyAppVersion4 MyAppVersion + ".0"
#ifndef StageDir
  #define StageDir "..\output\installer_stage"
#endif

[Setup]
AppId={{7E1B7A4C-9D3F-4A86-9C2E-5B4C1F0D8A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=CrForum
DefaultDirName={localappdata}\CrForum
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputBaseFilename=forum_setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
AllowNoIcons=yes
; The client may still briefly hold forum.exe: let Restart Manager close it, then
; overwrite the files (replaces the old .cmd "wait for the app to exit" loop).
; RestartApplications=no: [Run] relaunches the client, so don't restart it twice.
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion4}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany=CrForum
VersionInfoDescription=Forum Client Setup
VersionInfoTextVersion={#MyAppVersion4}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#StageDir}\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\uninstall.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Crforum:// URI scheme (per-user)
Root: HKCU; Subkey: "Software\Classes\Crforum"; ValueType: string; ValueName: ""; ValueData: "URL:ForumClient"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Crforum"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Crforum\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\Crforum\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
; NOTE: skipifsilent was removed on purpose: in /SILENT mode Setup now relaunches
; the client itself once the install finishes. Previously the .cmd wrapper did the
; "start" after install; the installer no longer goes through a .cmd helper.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall
