@echo off
setlocal

cd /d "%~dp0"

set "PS_SCRIPT=%~dp0package_gui_release.ps1"

if not exist "%PS_SCRIPT%" (
  echo [package-gui-release] PowerShell script not found: %PS_SCRIPT%
  exit /b 1
)

echo [package-gui-release] Calling script: %PS_SCRIPT% %*
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
exit /b %ERRORLEVEL%