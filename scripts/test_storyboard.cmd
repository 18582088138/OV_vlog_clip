@echo off
setlocal
cd /d "%~dp0.."
python scripts\test_storyboard.py %*
exit /b %ERRORLEVEL%