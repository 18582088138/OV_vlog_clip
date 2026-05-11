@echo off
setlocal
cd /d "%~dp0.."
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" (
	"%CONDA_PREFIX%\python.exe" scripts\test_e2e.py %*
) else (
	python scripts\test_e2e.py %*
)
exit /b %ERRORLEVEL%