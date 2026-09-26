@echo off
REM ============================================================
REM  Forum client installer (ASCII only - cmd.exe encoding safe)
REM  Copies payload, registers the Crforum:// URI scheme and the
REM  per-user uninstall entry, then starts the client.
REM  Optional switches:  /quiet
REM ============================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion
title Forum Client Setup

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "APPDIR=%LOCALAPPDATA%\CrForum"
set "EXE=%APPDIR%\forum.exe"
set "QUIET="
if /I "%~1"=="/quiet" set "QUIET=1"
if /I "%~1"=="/S" set "QUIET=1"

if not defined QUIET (
  echo.
  echo   Forum Client - Setup
  echo   -----------------------------------------------
  echo   Install dir : %APPDIR%
  echo   Data dir    : %%USERPROFILE%%\.Cr\forum
  echo.
)

if not exist "%SRC%\payload\forum.exe" (
  echo [ERROR] payload\forum.exe not found - the package is incomplete.
  if not defined QUIET pause
  exit /b 1
)

if not defined QUIET echo [1/4] Copying program files ...
if not exist "%APPDIR%" mkdir "%APPDIR%" >nul 2>&1
robocopy "%SRC%\payload" "%APPDIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo [ERROR] copy failed (robocopy errorlevel %ERRORLEVEL%).
  if not defined QUIET pause
  exit /b 1
)

if not defined QUIET echo [2/4] Installing registry entries ...
if exist "%SRC%\postinstall.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\postinstall.ps1" -Exe "%EXE%" -AppDir "%APPDIR%" -Version "1.0.0"
) else (
  echo [WARN] postinstall.ps1 missing - registry entries were not written.
)

if not defined QUIET echo [3/4] Registering Crforum:// handler ...
reg add "HKCU\Software\Classes\Crforum" /ve /t REG_SZ /d "URL:ForumClient" /f >nul
reg add "HKCU\Software\Classes\Crforum" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "HKCU\Software\Classes\Crforum\DefaultIcon" /ve /t REG_SZ /d "\"%EXE%\",0" /f >nul
reg add "HKCU\Software\Classes\Crforum\shell\open\command" /ve /t REG_SZ /d "\"%EXE%\" \"%%1\"" /f >nul

if not defined QUIET echo [4/4] Finishing ...
copy /y "%SRC%\uninstall.cmd" "%APPDIR%\uninstall.cmd" >nul 2>&1
if not defined QUIET (
  echo.
  echo   Done. Starting the client ...
)
start "" "%EXE%"
if not defined QUIET timeout /t 2 >nul
endlocal
exit /b 0
