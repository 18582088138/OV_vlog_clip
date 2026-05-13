@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

rem Default parameters (match package_gui_release.ps1 defaults)
set "OutputRoot=release"
set "ReleaseName="
set "SampleVideo=videos\2022yunqidahui.mp4"
set "SampleBgm=resource\bgm\002_sunny_piano_walk.mp3"
set "SkipZip=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="-SkipZip" (set "SkipZip=1" & shift & goto parse_args)
if /I "%~1"=="-OutputRoot" (set "OutputRoot=%~2" & shift & shift & goto parse_args)
if /I "%~1"=="-ReleaseName" (set "ReleaseName=%~2" & shift & shift & goto parse_args)
if /I "%~1"=="-SampleVideo" (set "SampleVideo=%~2" & shift & shift & goto parse_args)
if /I "%~1"=="-SampleBgm" (set "SampleBgm=%~2" & shift & shift & goto parse_args)
shift & goto parse_args

:args_done

echo [package-gui-release] Project script starting...

set "projectRoot=%~dp0"
set "distRoot=%projectRoot%dist\ov-video-editing-gui\"
set "exePath=%distRoot%ov-video-editing-gui.exe"
set "defaultConfig=%projectRoot%ov_video_editing_skills\gui\default_config.json"
set "modelScript=%projectRoot%ov_video_editing_skills\setup_ov_model.py"
set "selfCheckCmd=%projectRoot%scripts\release_self_check.cmd"
set "selfCheckPs=%projectRoot%scripts\release_self_check.ps1"
set "bgmRoot=%projectRoot%resource\bgm\"
set "localFfmpeg=%projectRoot%bin\ffmpeg.exe"
set "localFfprobe=%projectRoot%bin\ffprobe.exe"
set "sampleVideoPath=%projectRoot%%SampleVideo%"
set "sampleBgmPath=%projectRoot%%SampleBgm%"

rem derive base filenames for sample video and bgm
for %%F in ("%sampleVideoPath%") do set "sampleVideoName=%%~nxF"
for %%F in ("%sampleBgmPath%") do set "sampleBgmName=%%~nxF"

rem Extract version from __init__.py
set "initFile=%projectRoot%ov_video_editing_skills\__init__.py"
set "version="
for /f "usebackq delims=" %%L in (`findstr /R "__version__" "%initFile%" 2^>nul`) do (
  set "line=%%L"
  rem remove leading parts until =
  for /f "tokens=2 delims==" %%V in ("%%L") do set "verpart=%%V"
)
if defined verpart (
  set "version=!verpart: =!"
  set "version=!version:"=!
  set "version=!version:'=!
)
if not defined version set "version=0.0.0"

if "%ReleaseName%"=="" set "ReleaseName=ov-video-editing-gui-windows-v%version%"

set "outputBase=%projectRoot%%OutputRoot%\"
set "releaseDir=%outputBase%%ReleaseName%\"
set "zipPath=%outputBase%%ReleaseName%.zip"

echo [package-gui-release] Project root: %projectRoot%
echo [package-gui-release] Release dir: %releaseDir%

if not exist "%exePath%" (
  echo [ERROR] GUI executable not found: %exePath%
  exit /b 1
)
if not exist "%defaultConfig%" (
  echo [ERROR] Default config not found: %defaultConfig%
  exit /b 1
)
if not exist "%modelScript%" (
  echo [ERROR] Model helper script not found: %modelScript%
  exit /b 1
)
if not exist "%sampleVideoPath%" (
  echo [ERROR] Sample video not found: %sampleVideoPath%
  exit /b 1
)
if not exist "%sampleBgmPath%" (
  echo [ERROR] Sample BGM not found: %sampleBgmPath%
  exit /b 1
)

rem Reset release directory
if exist "%releaseDir%" (
  echo [package-gui-release] Removing existing release dir
  rmdir /s /q "%releaseDir%"
)
mkdir "%releaseDir%" 2>nul

if exist "%zipPath%" del /f /q "%zipPath%"

echo [package-gui-release] Copy GUI one-dir build
xcopy "%distRoot%*" "%releaseDir%\" /E /I /Y >nul

set "configDir=%releaseDir%config\"
set "scriptsDir=%releaseDir%scripts\"
set "samplesVideoDir=%releaseDir%samples\videos\"
set "resourceBgmDir=%releaseDir%resource\bgm\"
set "modelDir=%releaseDir%models\Qwen2.5-VL-7B-Instruct-int4\"
set "binDir=%releaseDir%bin\"
set "workspaceDir=%releaseDir%workspace_output\"

mkdir "%configDir%" "%scriptsDir%" "%samplesVideoDir%" "%resourceBgmDir%" "%modelDir%" "%binDir%" "%workspaceDir%" 2>nul

echo [package-gui-release] Copy config, sample video, and BGM assets
copy /Y "%defaultConfig%" "%configDir%default_config.json" >nul
copy /Y "%sampleVideoPath%" "%samplesVideoDir%%sampleVideoName%" >nul
xcopy /E /I /Y "%bgmRoot%*" "%resourceBgmDir%" >nul
copy /Y "%modelScript%" "%scriptsDir%setup_ov_model.py" >nul

rem copy release self-check command if exists (prefer CMD variant)
if exist "%selfCheckCmd%" (
  copy /Y "%selfCheckCmd%" "%scriptsDir%release_self_check.cmd" >nul
  echo [package-gui-release] Copied cmd self-check helper
) else if exist "%selfCheckPs%" (
  copy /Y "%selfCheckPs%" "%scriptsDir%release_self_check.ps1" >nul
  echo [package-gui-release] Copied ps1 self-check helper
) else (
  echo [WARNING] No release self-check helper found
)

rem Copy ffmpeg if present
if exist "%localFfmpeg%" if exist "%localFfprobe%" (
  echo [package-gui-release] Copy local ffmpeg binaries into release package
  copy /Y "%localFfmpeg%" "%binDir%ffmpeg.exe" >nul
  copy /Y "%localFfprobe%" "%binDir%ffprobe.exe" >nul
) else (
  echo [package-gui-release] Local ffmpeg binaries not found; release self-check script will handle download if requested
)

rem Create sample config JSON
set "sampleVideoRelative=.\samples\videos\%sampleVideoName%"
rem Build sample_gui_config.json
(
  echo {^
  echo   "video_input": ".\samples\videos\%sampleVideoName%",^
  echo   "user_request": "Create a 30-second vlog summary",^
  echo   "output_dir": ".\workspace_output",^
  echo   "model_dir": "{DEFAULT_MODEL_DIR}",^
  echo   "ffmpeg_path": "{DEFAULT_FFMPEG}",^
  echo   "font_file": "",^
  echo   "bgm_file": ".\resource\bgm\%sampleBgmName%",^
  echo   "bgm_style": "",^
  echo   "brief_path": "",^
  echo   "analysis_path": "",^
  echo   "storyboard_path": "",^
  echo   "device": "GPU",^
  echo   "ignore_existing_analysis": false,^
  echo   "skip_ffmpeg": false,^
  echo   "skip_model": false^
  echo }
 ) > "%configDir%sample_gui_config.json"

rem Create sample_media_paths.json
(
  echo {^
  echo   "launcher": ".\ov-video-editing-gui.exe",^
  echo   "default_config": ".\config\default_config.json",^
  echo   "sample_config": ".\config\sample_gui_config.json",^
  echo   "sample_video": ".\samples\videos\%sampleVideoName%",^
  echo   "bgm_dir": ".\resource\bgm",^
  echo   "sample_bgm": ".\resource\bgm\%sampleBgmName%",^
  echo   "model_target_dir": ".\models\Qwen2.5-VL-7B-Instruct-int4",^
  echo   "ffmpeg_target_path": ".\bin\ffmpeg.exe"^
  echo }
) > "%configDir%sample_media_paths.json"

rem Create helper CMD files
echo @echo off> "%scriptsDir%download_model_windows.cmd"
echo setlocal>> "%scriptsDir%download_model_windows.cmd"
echo set "MODEL_DIR=%%~dp0..\models\Qwen2.5-VL-7B-Instruct-int4" >> "%scriptsDir%download_model_windows.cmd"
echo echo [download-model] Recommended model repo: OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov >> "%scriptsDir%download_model_windows.cmd"
echo echo Copy or extract the model files into: %%MODEL_DIR%% >> "%scriptsDir%download_model_windows.cmd"
echo exit /b 0 >> "%scriptsDir%download_model_windows.cmd"

rem run_gui.cmd
(
  echo @echo off
  echo setlocal
  echo cd /d "%%~dp0"
  echo "%%~dp0ov-video-editing-gui.exe" --settings "%%~dp0config\default_config.json"
  echo exit /b %%ERRORLEVEL%%
) > "%releaseDir%run_gui.cmd"

rem run_gui_with_sample.cmd
(
  echo @echo off
  echo setlocal
  echo cd /d "%%~dp0"
  echo "%%~dp0ov-video-editing-gui.exe" --settings "%%~dp0config\sample_gui_config.json"
  echo exit /b %%ERRORLEVEL%%
) > "%releaseDir%run_gui_with_sample.cmd"

rem self_check_release.cmd -> prefer cmd helper inside scripts
(
  echo @echo off
  echo setlocal
  echo cd /d "%%~dp0"
  if exist "%scriptsDir%release_self_check.cmd" (
    echo "%%~dp0scripts\release_self_check.cmd" -ReleaseRoot "%%~dp0" -DownloadMissing
  ) else (
    echo powershell -NoProfile -ExecutionPolicy Bypass -File "%%~dp0scripts\release_self_check.ps1" -ReleaseRoot "%%~dp0" -DownloadMissing
  )
  echo exit /b %%ERRORLEVEL%%
) > "%releaseDir%self_check_release.cmd"

rem model & ffmpeg README
echo Place the OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov model files in this folder.> "%modelDir%README_PLACE_MODEL_HERE.txt"
echo Place ffmpeg.exe and ffprobe.exe in this folder.> "%binDir%README_PLACE_FFMPEG_HERE.txt"

rem Create release README
(
  echo ov-video-editing-skills Windows GUI Release
  echo ===========================================
  echo.
  echo 1. Extract the whole zip to any folder on Windows.
  echo 2. Run: run_gui.cmd
  echo 3. To preload the sample video and sample BGM: run_gui_with_sample.cmd
  echo.
  echo Package contents: see scripts and README files in the release.
) > "%releaseDir%README_RELEASE.txt"

if "%SkipZip%"=="0" (
  echo [package-gui-release] Creating zip: %zipPath%
  if not exist "%outputBase%" (
      echo Directory "%outputBase%" does not exist. Creating it...
      mkdir "%outputBase%"
  )

  rem Verify the release folder exists
  if not exist "%outputBase%%ReleaseName%\" (
    echo [ERROR] Release source folder not found: "%outputBase%%ReleaseName%\"
    echo [DEBUG] Listing contents of %outputBase%:
    dir "%outputBase%" /b
    exit /b 1
  )

  rem Count files to ensure folder is not empty
  set "file_count=0"
  for /f %%C in ('dir "%outputBase%%ReleaseName%\" /a /s /b ^| find /v "" /c') do set "file_count=%%C"
  echo [DEBUG] File count in source: %file_count%
  if "%file_count%"=="0" (
    echo [ERROR] Release source folder is empty: "%outputBase%%ReleaseName%\" 
    exit /b 1
  )

  echo [DEBUG] Source: "%outputBase%%ReleaseName%\"
  echo [DEBUG] Archive: "%zipPath%"

  rem Prefer tar.exe if available
  where tar.exe >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] tar.exe not found. Attempting PowerShell Compress-Archive as fallback.
    powershell -NoProfile -Command "Compress-Archive -Path '%outputBase%%ReleaseName%' -DestinationPath '%zipPath%' -Force"
    if errorlevel 1 (
      echo [ERROR] PowerShell Compress-Archive failed to create %zipPath%
      exit /b 1
    )
  ) else (
    echo [DEBUG] Using tar.exe to create archive
    pushd "%outputBase%"
    if errorlevel 1 (
      echo [ERROR] Failed to enter output directory: "%outputBase%"
      exit /b 1
    )
    tar.exe -a -cf "%zipPath%" "%ReleaseName%"
    set "tar_rc=!ERRORLEVEL!"
    popd
    if not "!tar_rc!"=="0" (
      echo [WARNING] tar.exe failed with rc=!tar_rc!; falling back to PowerShell Compress-Archive
      powershell -NoProfile -Command "Compress-Archive -Path '%outputBase%%ReleaseName%' -DestinationPath '%zipPath%' -Force"
      if errorlevel 1 (
        echo [ERROR] PowerShell Compress-Archive also failed
        exit /b 1
      )
    )
  )
)

echo [package-gui-release] Release ready: %releaseDir%
if "%SkipZip%"=="0" echo [package-gui-release] Zip ready: %zipPath%

endlocal
exit /b 0