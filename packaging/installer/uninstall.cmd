@echo off
REM ============================================================
REM  Forum client uninstaller (ASCII only - cmd.exe encoding safe)
REM  Removes registry entries, shortcuts and the program directory.
REM  User data in %USERPROFILE%\.Cr\forum is KEPT unless /purge.
REM ============================================================
chcp 65001 >nul 2>&1
setlocal
set "APPDIR=%LOCALAPPDATA%\CrForum"
set "QUIET="
set "PURGE="
if /I "%~1"=="/quiet" set "QUIET=1"
if /I "%~1"=="/purge" set "PURGE=1"
if /I "%~2"=="/purge" set "PURGE=1"

if not defined QUIET (
  echo.
  echo   Forum Client - Uninstall
  echo   -----------------------------------------------
  echo   Program dir : %APPDIR%
  if defined PURGE (
    echo   User data   : %%USERPROFILE%%\.Cr\forum  WILL BE DELETED
  ) else (
    echo   User data   : %%USERPROFILE%%\.Cr\forum  will be kept
  )
  echo.
  choice /C YN /N /M "Continue? [Y/N] "
  if errorlevel 2 exit /b 0
)

echo Removing registry entries ...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\CrForum" /f >nul 2>&1
reg delete "HKCU\Software\Classes\Crforum" /f >nul 2>&1

echo Removing shortcuts ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$n = -join ([char]0x5996,[char]0x7CBE,[char]0x8BBA,[char]0x575B,[char]0x5BA2,[char]0x6237,[char]0x7AEF); Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Programs')) ($n + '.lnk')); Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Desktop')) ($n + '.lnk'))" >nul 2>&1

echo Removing program files ...
if exist "%APPDIR%\forum.exe" (
  taskkill /IM forum.exe /F >nul 2>&1
  timeout /t 1 >nul
)
if exist "%APPDIR%" rmdir /s /q "%APPDIR%" >nul 2>&1

if defined PURGE (
  echo Removing user data ...
  if exist "%USERPROFILE%\.Cr\forum" rmdir /s /q "%USERPROFILE%\.Cr\forum" >nul 2>&1
)

echo Done.
if not defined QUIET (
  timeout /t 2 >nul
)
endlocal
exit /b 0
