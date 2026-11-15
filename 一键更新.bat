@echo off
chcp 65001 >nul
title AI 跑团 · 一键更新
cd /d "%~dp0"
if not exist "%~dp0server.py" (
    echo ======================================================================
    echo   [无法更新] 请先将整个压缩包完整解压到文件夹后，再运行一键更新！
    echo ======================================================================
    pause
    exit /b 1
)
if exist "%~dp0runtime\python\python.exe" (
    "%~dp0runtime\python\python.exe" -B server.py --update %*
) else (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [未检测到可用的 Python 3.9+ 环境，请下载自带运行环境的 Windows 纯净整合包或先安装 Python]
        pause
        exit /b 1
    )
    python -B server.py --update %*
)
echo.
pause
