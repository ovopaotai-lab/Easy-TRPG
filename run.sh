#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
mkdir -p "$DIR/models"
if [ ! -e "$DIR/model" ]; then
    ln -s "models" "$DIR/model" 2>/dev/null || mkdir -p "$DIR/model"
fi
chmod +x "$DIR/engine/strata/engine/strata" "$DIR/engine/strata/engine/strata-vision" "$DIR/engine/llama/llama-server" 2>/dev/null || true
export LD_LIBRARY_PATH="$DIR/engine/llama:$DIR/engine/strata/engine${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
echo "======================================================================"
echo "  AI 跑团 (alpha 1.4) 启动中..."
echo "  模型 (.gguf) 放入 model/ 即可自动识别"
echo "======================================================================"
PY_BIN="python3"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    PY_BIN="python"
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
exec "$PY_BIN" -B server.py "$@"
