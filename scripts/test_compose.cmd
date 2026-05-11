@echo off
setlocal
cd /d "%~dp0.."
python scripts\test_compose.py %*
exit /b %ERRORLEVEL%