@echo off
setlocal

cd /d "%~dp0"

set "SPEC_FILE=%~dp0ov_video_editing_e2e.spec"
set "PYINSTALLER_CMD="

if not exist "%SPEC_FILE%" (
  echo [build-e2e-exe] Spec file not found: %SPEC_FILE%
  exit /b 1
)

if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\Scripts\pyinstaller.exe" (
  set "PYINSTALLER_CMD=%CONDA_PREFIX%\Scripts\pyinstaller.exe"
) else (
  where pyinstaller >nul 2>nul
  if not errorlevel 1 (
    set "PYINSTALLER_CMD=pyinstaller"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 (
      set "PYINSTALLER_CMD=python -m PyInstaller"
    )
  )
)

if "%PYINSTALLER_CMD%"=="" (
  echo [build-e2e-exe] PyInstaller not found. Install dependencies in the current conda environment first:
  echo     python -m pip install -r requirements-build.txt
  exit /b 1
)

echo [build-e2e-exe] Working directory: %CD%
echo [build-e2e-exe] Using spec: %SPEC_FILE%
echo [build-e2e-exe] Command: %PYINSTALLER_CMD% "%SPEC_FILE%" --clean %*

call %PYINSTALLER_CMD% "%SPEC_FILE%" --clean %*
if errorlevel 1 (
  echo [build-e2e-exe] Build failed.
  exit /b 1
)

if exist "%~dp0dist\ov-video-editing-e2e.exe" (
  echo [build-e2e-exe] Build complete: %~dp0dist\ov-video-editing-e2e.exe
)

exit /b 0