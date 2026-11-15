#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -f "$DIR/server.py" ] || [ ! -f "$DIR/enterprise_engine.py" ] || [ ! -f "$DIR/static/index.html" ]; then
    echo "======================================================================"
    echo "  [启动受阻] 未检测到完整程序文件，请先完整解压压缩包后再运行 ./run.sh"
    echo "======================================================================"
    exit 1
fi
mkdir -p "$DIR/models"
if [ ! -e "$DIR/model" ]; then
    ln -s "models" "$DIR/model" 2>/dev/null || mkdir -p "$DIR/model"
fi
chmod +x "$DIR/engine/strata/engine/strata" "$DIR/engine/strata/engine/strata-vision" "$DIR/engine/llama/llama-server" 2>/dev/null || true
export LD_LIBRARY_PATH="$DIR/engine/llama:$DIR/engine/strata/engine${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TRPG_SUPERVISOR=1
echo "======================================================================"
echo "  AI 跑团 启动中..."
echo "  模型 (.gguf) 放入 model/ 即可自动识别"
echo "======================================================================"
PY_BIN="python3"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    PY_BIN="python"
fi
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    echo "======================================================================"
    echo "  [启动受阻] 未检测到 Python3 环境，请先执行: sudo apt update && sudo apt install -y python3 python3-pip"
    echo "======================================================================"
    exit 1
fi
if ! "$PY_BIN" -c "import fastapi, uvicorn, httpx, PIL, multipart" >/dev/null 2>&1; then
    echo "[正在为您自动安装所需 Python 依赖包...]"
    "$PY_BIN" -m pip install --timeout 15 -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages 2>/dev/null || \
    "$PY_BIN" -m pip install --timeout 15 -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
    "$PY_BIN" -m pip install -r requirements.txt --break-system-packages 2>/dev/null || \
    "$PY_BIN" -m pip install -r requirements.txt 2>/dev/null || \
    "$PY_BIN" -m pip install fastapi uvicorn httpx pydantic pillow python-multipart --break-system-packages 2>/dev/null || \
    "$PY_BIN" -m pip install fastapi uvicorn httpx pydantic pillow python-multipart
fi
EXTRA_ARGS=()
while true; do
    set +e
    "$PY_BIN" -B server.py "${EXTRA_ARGS[@]}" "$@"
    RC=$?
    set -e
    if [ "$RC" -eq 42 ]; then
        EXTRA_ARGS=(--no-browser)
        echo ""
        echo "[一键更新完成，正在自动重启 AI 跑团服务...]"
        continue
    fi
    exit "$RC"
done
