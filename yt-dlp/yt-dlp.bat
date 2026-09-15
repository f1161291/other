@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title YT-DLP 下载工具

:: ============================================
:: YT-DLP 下载脚本 (Windows BAT 版)
:: 最佳质量 / 不下载字幕 / 默认代理
:: 下载到脚本同目录的 downloads 文件夹
:: 文件名使用网站原始文件名
:: 支持独立 yt-dlp.exe
:: ============================================

color 0A
echo ==================================================
echo            YT-DLP 下载工具
echo ==================================================
echo.

:: ---------- 代理配置 ----------
set "PROXY_ADDR=socks5://192.168.0.76:7893"
set "PROXY_OPT=--proxy %PROXY_ADDR%"

:: ---------- 下载目录（脚本同目录下的 downloads）----------
set "DOWNLOAD_PATH=%~dp0downloads"
if not exist "%DOWNLOAD_PATH%" mkdir "%DOWNLOAD_PATH%"

:: ---------- 检测 yt-dlp ----------
echo [1/3] 检查 yt-dlp 环境...

set "YTDLP_CMD="

if exist "%~dp0yt-dlp.exe" (
    set "YTDLP_CMD=%~dp0yt-dlp.exe"
    goto :ytdlp_found
)
if exist "%~dp0bin\yt-dlp.exe" (
    set "YTDLP_CMD=%~dp0bin\yt-dlp.exe"
    goto :ytdlp_found
)
if exist "%USERPROFILE%\Desktop\yt-dlp.exe" (
    set "YTDLP_CMD=%USERPROFILE%\Desktop\yt-dlp.exe"
    goto :ytdlp_found
)

where yt-dlp >nul 2>nul
if !errorlevel! equ 0 (
    set "YTDLP_CMD=yt-dlp"
    goto :ytdlp_found
)

python -m yt_dlp --version >nul 2>nul
if !errorlevel! equ 0 (
    set "YTDLP_CMD=python -m yt_dlp"
    goto :ytdlp_found
)

py -m yt_dlp --version >nul 2>nul
if !errorlevel! equ 0 (
    set "YTDLP_CMD=py -m yt_dlp"
    goto :ytdlp_found
)

echo.
echo [X] 未检测到 yt-dlp
echo     请下载 yt-dlp.exe 放到脚本同目录
echo     下载地址: https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
echo.
pause
exit /b 1

:ytdlp_found
echo [√] yt-dlp: !YTDLP_CMD!
echo [√] 代理:   %PROXY_ADDR%
echo [√] 保存至: %DOWNLOAD_PATH%
echo.

:: ---------- 输入 URL ----------
echo [2/3] 请输入下载地址
echo      (视频链接或频道链接均可)
echo.
set /p "URL=URL: "

if "%URL%"=="" (
    echo.
    echo [X] URL 不能为空！
    pause
    exit /b 1
)

:: ---------- 判断是否为频道 ----------
set "IS_CHANNEL=0"

echo %URL% | findstr /i "youtube.com/@ youtube.com/c/ youtube.com/channel/ youtube.com/user/" >nul
if !errorlevel! equ 0 (
    echo %URL% | findstr /i "/watch? /video/" >nul
    if !errorlevel! neq 0 set "IS_CHANNEL=1"
)

echo %URL% | findstr /i "bilibili.com/space/ bilibili.com/channel/" >nul
if !errorlevel! equ 0 set "IS_CHANNEL=1"

echo %URL% | findstr /i "tiktok.com/@" >nul
if !errorlevel! equ 0 set "IS_CHANNEL=1"

set "CHANNEL_OPTS="
if "!IS_CHANNEL!"=="1" (
    echo.
    echo [!] 检测到频道/播放列表链接，将下载该频道所有视频
    set /p "CONFIRM=确认继续？(y/n): "
    if /i not "!CONFIRM!"=="y" (
        echo 已取消下载
        pause
        exit /b 0
    )
    set "CHANNEL_OPTS=--yes-playlist --download-archive downloaded.txt"
)
echo.

:: ---------- 开始下载 ----------
echo [3/3] 开始下载...
echo ==================================================
echo   URL:      %URL%
echo   保存路径: %DOWNLOAD_PATH%
echo   类型:     %IS_CHANNEL% (1=频道, 0=单视频)
echo   代理:     %PROXY_ADDR%
echo ==================================================
echo.

cd /d "%DOWNLOAD_PATH%"

"%YTDLP_CMD%" ^
    -f "bestvideo+bestaudio/best" ^
    --merge-output-format mp4 ^
    -o "%%(title)s.%%(ext)s" ^
    --no-warnings ^
    --progress ^
    --ignore-errors ^
    --no-overwrites ^
    %PROXY_OPT% ^
    %CHANNEL_OPTS% ^
    "%URL%"

if %errorlevel% equ 0 (
    echo.
    echo ==================================================
    echo   [√] 下载完成！
    echo   文件保存在: %DOWNLOAD_PATH%
    echo ==================================================
) else (
    echo.
    echo ==================================================
    echo   [X] 下载出错，请检查 URL、代理或网络连接
    echo ==================================================
)

echo.
set /p "AGAIN=是否继续下载？(y/n): "
if /i "%AGAIN%"=="y" (
    cls
    goto :start
)

echo.
echo 感谢使用！再见！
pause
exit /b 0

:start
:: 跳转回开头（用于重新下载）
goto :eof