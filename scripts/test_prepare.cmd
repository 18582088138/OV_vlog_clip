@echo off
setlocal
cd /d "%~dp0.."
python scripts\test_prepare.py %*
exit /b %ERRORLEVEL%
