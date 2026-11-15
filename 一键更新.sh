#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -f "$DIR/server.py" ]; then
    echo "======================================================================"
    echo "  [无法更新] 请先将整个压缩包完整解压到文件夹后，再运行 ./一键更新.sh"
    echo "======================================================================"
    exit 1
fi
PY_BIN="python3"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    PY_BIN="python"
fi
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    echo "[未检测到 Python3 环境，请先执行: sudo apt update && sudo apt install -y python3]"
    exit 1
fi
exec "$PY_BIN" -B server.py --update "$@"
