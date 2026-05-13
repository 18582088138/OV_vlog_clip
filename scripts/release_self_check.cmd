@echo off
setlocal enabledelayedexpansion

rem release_self_check.cmd - CMD-based release self-check and optional ffmpeg download
rem Usage: release_self_check.cmd [-ReleaseRoot <path>] [-DownloadMissing] [-FfmpegUrl <url>] [-ModelSource hf-mirror|huggingface] [-ModelRepo <repo>]

set "RELEASEROOT="
set "DOWNLOADMISSING=0"
set "FFMPEGURL=https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-full_build.zip"
set "MODELSOURCE=hf-mirror"
set "MODELREPO=OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov"

:parse_args
if "%~1"=="" goto args_parsed
if /I "%~1"=="-ReleaseRoot" (
    set "RELEASEROOT=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="-DownloadMissing" (
    set "DOWNLOADMISSING=1"
    shift
    goto parse_args
)
if /I "%~1"=="-FfmpegUrl" (
    set "FFMPEGURL=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="-ModelSource" (
    set "MODELSOURCE=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="-ModelRepo" (
    set "MODELREPO=%~2"
    shift
    shift
    goto parse_args
)
rem unknown arg, skip
shift
goto parse_args

:args_parsed
if "%RELEASEROOT%"=="" (
    rem default to parent of script
    pushd "%~dp0\.." >nul 2>&1
    for /f "usebackq delims=" %%D in (`cd`) do set "RELEASEROOT=%%D"
    popd >nul 2>&1
)

echo [release-self-check] Release root: %RELEASEROOT%

set "CONFIGDIR=%RELEASEROOT%\config"
set "SAMPLEDIR=%RELEASEROOT%\samples\videos"
set "BGMDIR=%RELEASEROOT%\resource\bgm"
set "BINDIR=%RELEASEROOT%\bin"
set "MODELDIR=%RELEASEROOT%\models\Qwen2.5-VL-7B-Instruct-int4"

setlocal disableDelayedExpansion
set "missing_count=0"
set "missing_list="

call :check_item "GUI launcher" "%RELEASEROOT%\ov-video-editing-gui.exe"
call :check_item "default config" "%CONFIGDIR%\default_config.json"
call :check_item "sample config" "%CONFIGDIR%\sample_gui_config.json"
call :check_item "sample media paths" "%CONFIGDIR%\sample_media_paths.json"

rem sample videos count
set "sample_count=0"
if exist "%SAMPLEDIR%" (
    for /f "usebackq delims=" %%F in (`dir /b "%SAMPLEDIR%" 2^>nul`) do (
        set /a sample_count+=1
    )
)
if %sample_count% gtr 0 (
    echo [release-self-check] OK: sample videos (%sample_count%)
) else (
    echo [release-self-check] Missing: sample videos -> %SAMPLEDIR%
    call :mark_missing "sample videos"
)

rem bgm files
set "bgm_count=0"
if exist "%BGMDIR%" (
    for /f "usebackq delims=" %%F in (`dir /b "%BGMDIR%\*.mp3" 2^>nul`) do set /a bgm_count+=1
    for /f "usebackq delims=" %%F in (`dir /b "%BGMDIR%\*.wav" 2^>nul`) do set /a bgm_count+=1
    for /f "usebackq delims=" %%F in (`dir /b "%BGMDIR%\*.m4a" 2^>nul`) do set /a bgm_count+=1
)
if %bgm_count% gtr 0 (
    echo [release-self-check] OK: BGM assets (%bgm_count%)
) else (
    echo [release-self-check] Missing: BGM assets -> %BGMDIR%
    call :mark_missing "bgm assets"
)

rem ffmpeg
set "ffmpeg_path=%BINDIR%\ffmpeg.exe"
set "ffprobe_path=%BINDIR%\ffprobe.exe"
if exist "%ffmpeg_path%" if exist "%ffprobe_path%" (
    echo [release-self-check] OK: ffmpeg / ffprobe
) else (
    if "%DOWNLOADMISSING%"=="1" (
        echo [release-self-check] ffmpeg missing; downloading bundle from %FFMPEGURL%
        call :download_ffmpeg "%FFMPEGURL%" "%BINDIR%"
        if errorlevel 1 (
            echo [release-self-check] ERROR: ffmpeg download or extraction failed
            call :mark_missing "ffmpeg"
        ) else (
            if exist "%ffmpeg_path%" if exist "%ffprobe_path%" (
                echo [release-self-check] OK: ffmpeg / ffprobe (downloaded)
            ) else (
                echo [release-self-check] Missing after download: ffmpeg / ffprobe
                call :mark_missing "ffmpeg"
            )
        )
    ) else (
        echo [release-self-check] Missing: ffmpeg / ffprobe -> %ffmpeg_path% , %ffprobe_path%
        call :mark_missing "ffmpeg"
    )
)

rem model
call :is_model_ready "%MODELDIR%"
if errorlevel 1 (
    if "%DOWNLOADMISSING%"=="1" (
        echo [release-self-check] Model missing; automatic download of full model snapshots is not supported in this CMD script.
        echo [release-self-check] Please use the PowerShell helper or the Python script to download model snapshots from %MODELSOURCE%.
        echo [release-self-check] Model repo: %MODELREPO%
        call :mark_missing "model"
    ) else (
        echo [release-self-check] Missing: model files -> %MODELDIR%
        call :mark_missing "model"
    )
) else (
    echo [release-self-check] OK: model files
)

rem final evaluation
setlocal enabledelayedexpansion
if !missing_count! EQU 0 (
    rem ensure ffmpeg/model ready
    if exist "%ffmpeg_path%" if exist "%ffprobe_path%" (
        call :is_model_ready "%MODELDIR%"
        if errorlevel 1 (
            echo [release-self-check] Core dependencies ready, but some optional assets are missing: !missing_list!
            endlocal & endlocal & exit /b 0
        ) else (
            echo [release-self-check] All checks passed. Release package is ready.
            endlocal & endlocal & exit /b 0
        )
    ) else (
        echo [release-self-check] Release package is still incomplete. Missing: !missing_list!
        endlocal & endlocal & exit /b 1
    )
) else (
    echo [release-self-check] Release package is still incomplete. Missing: !missing_list!
    endlocal & endlocal & exit /b 1
)

:check_item
rem %1 = name, %2 = path
if exist "%~2" (
    echo [release-self-check] OK: %~1
) else (
    echo [release-self-check] Missing: %~1 -> %~2
    call :mark_missing "%~1"
)
goto :eof

:mark_missing
setlocal enabledelayedexpansion
set "name=%~1"
for /f "usebackq delims=" %%A in (`echo !missing_list!`) do set "tmp=%%A"
if defined tmp (
    set "missing_list=!missing_list!, %name%"
    set /a missing_count+=1
else
    set "missing_list=%name%"
    set /a missing_count+=1
fi
endlocal & set "missing_list=%missing_list%" & set "missing_count=%missing_count%"
goto :eof

:is_model_ready
set "md=%~1"
if not exist "%md%" exit /b 1
set "xmlcount=0"
for /f "usebackq delims=" %%F in (`dir /b "%md%\*.xml" 2^>nul`) do set /a xmlcount+=1
set "bincount=0"
for /f "usebackq delims=" %%F in (`dir /b "%md%\*.bin" 2^>nul`) do set /a bincount+=1
if %xmlcount% GTR 0 if %bincount% GTR 0 (
    exit /b 0
) else (
    exit /b 1
)

:download_ffmpeg
set "url=%~1"
set "bindir=%~2"
set "tmproot=%TEMP%\ov-video-editing-ffmpeg-%RANDOM%"
set "zippath=%tmproot%\ffmpeg.zip"
set "extractdir=%tmproot%\extract"
md "%tmproot%" 2>nul
md "%extractdir%" 2>nul
md "%bindir%" 2>nul

echo [release-self-check] Downloading %url% to %zippath%
curl -L -o "%zippath%" "%url%"
if errorlevel 1 (
    echo [release-self-check] ERROR: curl failed to download ffmpeg bundle
    rd /s /q "%tmproot%" 2>nul
    exit /b 1
)

rem attempt to extract with tar (present on modern Windows)
where tar >nul 2>nul
if errorlevel 0 (
    tar -xf "%zippath%" -C "%extractdir%"
    if errorlevel 1 (
        echo [release-self-check] ERROR: tar failed to extract
        rd /s /q "%tmproot%" 2>nul
        exit /b 1
    )
    goto :ff_extract_search
) else (
    echo [release-self-check] ERROR: no 'tar' available to extract zip archive. Please extract %zippath% manually into a folder and copy ffmpeg.exe/ffprobe.exe into %bindir%
    rd /s /q "%tmproot%" 2>nul
    exit /b 1
)

:ff_extract_search
set "found_ffmpeg="
set "found_ffprobe="
for /r "%extractdir%" %%F in (ffmpeg.exe) do (
    if not defined found_ffmpeg set "found_ffmpeg=%%F"
)
for /r "%extractdir%" %%F in (ffprobe.exe) do (
    if not defined found_ffprobe set "found_ffprobe=%%F"
)

if defined found_ffmpeg if defined found_ffprobe (
    echo [release-self-check] Found ffmpeg: %found_ffmpeg%
    echo [release-self-check] Found ffprobe: %found_ffprobe%
    copy /Y "%found_ffmpeg%" "%bindir%\ffmpeg.exe" >nul
    copy /Y "%found_ffprobe%" "%bindir%\ffprobe.exe" >nul
    rd /s /q "%tmproot%" 2>nul
    exit /b 0
) else (
    echo [release-self-check] ERROR: extracted archive does not contain ffmpeg.exe/ffprobe.exe
    rd /s /q "%tmproot%" 2>nul
    exit /b 1
)
