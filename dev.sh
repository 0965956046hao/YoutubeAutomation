#!/bin/bash
# Run YT Recent Videos: backend (uvicorn :8001) + frontend (Next.js :3001)
# Usage:
#   ./dev.sh                 # backend chạy --reload (tiện dev)
#   YTV_NO_RELOAD=1 ./dev.sh # backend KHÔNG --reload (upload/download dài)

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

free_port() {
  local port="$1"
  local pids
  # `|| true` bắt buộc: lsof trả exit 1 khi KHÔNG có listener → với `set -e`
  # script sẽ thoát ngay. Luôn trả 0 để tiếp tục.
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "  -> freeing port $port (pid: $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}
echo "==> Freeing old ports (8001, 3001)"
free_port 8001
free_port 3001

BACKEND_PID=""
cleanup() {
  echo ""
  echo "Stopping backend (${BACKEND_PID:-?})..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "All stopped."
}
trap cleanup INT TERM EXIT

# Python: ưu tiên backend/.venv, fallback python3 hệ thống
if [ -x "$BACKEND/.venv/bin/python" ]; then
  PY="$BACKEND/.venv/bin/python"
elif [ -x "$BACKEND/.venv/bin/uvicorn" ]; then
  PY=""
else
  echo "!! Chưa có backend/.venv — tạo mới? (y/N)"
  read -r ans
  if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    python3 -m venv "$BACKEND/.venv"
    # Một số bản python macOS tạo venv thiếu pip → bootstrap lại cho chắc
    "$BACKEND/.venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$BACKEND/.venv/bin/python" -m pip install -r "$BACKEND/requirements.txt"
  fi
  PY="$BACKEND/.venv/bin/python"
fi

# Xóa .next production bẩn (nếu từng `npm run build`) để `next dev` phục vụ CSS đúng
if [ -d "$FRONTEND/.next/standalone" ]; then
  echo "==> Removing polluted production .next (standalone)"
  rm -rf "$FRONTEND/.next"
fi

if [ ! -x "$FRONTEND/node_modules/.bin/next" ]; then
  echo "==> Installing frontend deps (lần đầu / cài dở)"
  (cd "$FRONTEND" && npm install)
fi

if [ "${YTV_NO_RELOAD:-0}" = "1" ]; then
  RELOAD_FLAG=""
  echo "==> Starting backend  http://localhost:8001  (KHÔNG --reload)"
else
  RELOAD_FLAG="--reload"
  echo "==> Starting backend  http://localhost:8001"
fi
(
  cd "$BACKEND"
  if [ -n "$PY" ]; then
    exec "$PY" -m uvicorn app.main:app $RELOAD_FLAG --port 8001
  else
    exec .venv/bin/uvicorn app.main:app $RELOAD_FLAG --port 8001
  fi
) &
BACKEND_PID=$!

echo "==> Starting frontend http://localhost:3001"
(cd "$FRONTEND" && exec npm run dev)
