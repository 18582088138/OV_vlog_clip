@echo off
setlocal
cd /d "%~dp0.."
python scripts\test_analyze.py %*
exit /b %ERRORLEVEL%
