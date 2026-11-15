#!/bin/bash
# 整体启动脚本：先启动后端（langgraph dev），再启动前端
set -e
export PYTHONUTF8=1
ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT/backend" && langgraph dev &
BACKEND_PID=$!
trap "kill $BACKEND_PID" EXIT

cd "$ROOT/frontend" && npm run dev
