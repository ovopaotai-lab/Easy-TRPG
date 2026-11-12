@echo off
chcp 65001 >nul
title AI 跑团 (alpha 1.4)
cd /d "%~dp0"
if not exist "%~dp0models" mkdir "%~dp0models"
if not exist "%~dp0model" mkdir "%~dp0model"
echo ======================================================================
echo   AI 跑团 (alpha 1.4) 启动中...
echo   模型 (.gguf) 放入 model/ 即可识别
echo ======================================================================
if exist "%~dp0runtime\python\python.exe" (
    "%~dp0runtime\python\python.exe" -B server.py %*
) else (
    python -c "import fastapi, uvicorn, httpx, PIL, multipart" >nul 2>&1
    if errorlevel 1 (
        echo [正在为您自动安装所需 Python 依赖包...]
        python -m pip install --timeout 15 -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || (
            echo [完整依赖安装受阻，正在为您安装核心 Web 运行依赖...]
            python -m pip install --timeout 15 fastapi uvicorn httpx pydantic pillow python-multipart -i https://pypi.tuna.tsinghua.edu.cn/simple || python -m pip install fastapi uvicorn httpx pydantic pillow python-multipart
        )
    )
    python -B server.py %*
)
pause
