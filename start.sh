#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== gaosi-tutor 启动 ==="

echo "[1/3] 启动后端 (FastAPI :8000)..."
cd "$ROOT/backend"
if [ ! -d "venv" ]; then
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt -q
fi
./venv/bin/python run.py &
BACKEND_PID=$!

echo "[2/3] 启动前端 (Vue :5173)..."
cd "$ROOT/frontend"
if [ ! -x "node_modules/.bin/vite" ]; then
  npm install --no-audit --no-fund --silent
fi
./node_modules/.bin/vite &
FRONTEND_PID=$!

echo "[3/3] 服务已启动"
echo ""
echo "  孩子模式: http://localhost:5173/"
echo "  家长模式: http://localhost:5173/parent"
echo "  后端 API: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
