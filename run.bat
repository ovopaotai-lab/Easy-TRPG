@echo off
chcp 65001 >nul
title AI 跑团 (Easy-TRPG)
cd /d "%~dp0"
if not exist "%~dp0server.py" goto :err_not_extracted
if not exist "%~dp0enterprise_engine.py" goto :err_not_extracted
if not exist "%~dp0static\index.html" goto :err_not_extracted

if not exist "%~dp0models" mkdir "%~dp0models"
if not exist "%~dp0model" mkdir "%~dp0model"
set "TRPG_SUPERVISOR=1"
set "TRPG_EXTRA_ARGS="
echo ======================================================================
echo   AI 跑团 启动中...
echo   模型 (.gguf) 放入 model/ 即可识别
echo ======================================================================
:server_loop
if exist "%~dp0runtime\python\python.exe" (
    "%~dp0runtime\python\python.exe" -B server.py %TRPG_EXTRA_ARGS% %*
) else (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if errorlevel 1 goto :err_no_python
    python -c "import fastapi, uvicorn, httpx, PIL, multipart" >nul 2>&1
    if errorlevel 1 (
        echo [正在为您自动安装所需 Python 依赖包...]
        python -m pip install --timeout 15 -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || (
            echo [完整依赖安装受阻，正在为您安装核心 Web 运行依赖...]
            python -m pip install --timeout 15 fastapi uvicorn httpx pydantic pillow python-multipart -i https://pypi.tuna.tsinghua.edu.cn/simple || python -m pip install fastapi uvicorn httpx pydantic pillow python-multipart
        )
    )
    python -B server.py %TRPG_EXTRA_ARGS% %*
)
if "%ERRORLEVEL%"=="42" (
    set "TRPG_EXTRA_ARGS=--no-browser"
    echo.
    echo [一键更新完成，正在自动重启 AI 跑团服务...]
    goto server_loop
)
if not "%ERRORLEVEL%"=="0" pause
exit /b 0

:err_not_extracted
echo ======================================================================
echo   [启动受阻] 未检测到完整的程序文件！
echo.
echo   常见原因：您直接在压缩包（WinRAR / 7-Zip / 资源管理器预览）里双击了启动脚本。
echo   解决方法：请先将整个压缩包【完整解压】到普通文件夹（例如 D:\AI跑团工作台），
echo             再进入解压后的文件夹双击「一键启动_AI跑团工作台.bat」！
echo ======================================================================
pause
exit /b 1

:err_no_python
echo ======================================================================
echo   [启动受阻] 当前为轻量「API 纯净版」，未检测到可用的 Python 3.9+ 环境！
echo.
echo   解决方法（二选一）：
echo   1. [推荐新手] 下载自带完整运行环境的「Windows 纯净整合包」，解压即玩免装环境；
echo   2. 或前往 https://www.python.org 安装 Python 3.11 / 3.12（安装时勾选 Add to PATH）。
echo ======================================================================
pause
exit /b 1
