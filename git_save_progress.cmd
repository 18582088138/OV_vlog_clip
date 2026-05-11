@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist ".git" (
  echo [git] 当前目录尚未初始化 Git 仓库，正在初始化...
  git init -b main
  if errorlevel 1 (
    echo [git] Git 初始化失败。
    exit /b 1
  )
)

for /f "delims=" %%i in ('git config user.name 2^>nul') do set "GIT_USER_NAME=%%i"
for /f "delims=" %%i in ('git config user.email 2^>nul') do set "GIT_USER_EMAIL=%%i"

if "%GIT_USER_NAME%"=="" (
  echo [git] 未检测到 git user.name，请先执行：
  echo         git config user.name "Your Name"
  exit /b 1
)

if "%GIT_USER_EMAIL%"=="" (
  echo [git] 未检测到 git user.email，请先执行：
  echo         git config user.email "you@example.com"
  exit /b 1
)

set "COMMIT_MSG=%*"
if "%COMMIT_MSG%"=="" set "COMMIT_MSG=checkpoint: save current development progress"

echo [git] 当前仓库状态：
git status --short
if errorlevel 1 exit /b 1

echo.
echo [git] 即将提交的信息：
echo         %COMMIT_MSG%
echo.
set /p "CONFIRM=继续执行 git add / commit ? [Y/N]: "
if /I not "%CONFIRM%"=="Y" (
  echo [git] 已取消。
  exit /b 0
)

git add .
if errorlevel 1 (
  echo [git] git add 失败。
  exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
  git commit -m "%COMMIT_MSG%"
  if errorlevel 1 (
    echo [git] git commit 失败。
    exit /b 1
  )
  echo [git] 提交完成。
  git log -1 --oneline
  exit /b 0
)

echo [git] 没有可提交的变更。
exit /b 0
