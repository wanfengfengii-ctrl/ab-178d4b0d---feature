#!/usr/bin/env bash
# verify 一次性服务入口: 代码测试 -> 前端构建 -> API 冒烟。
# 任一步失败立即以非零退出码结束, 全部通过则退出 0。
set -euo pipefail

# 容器内固定 /app; 本地直接运行时可用 APP_DIR 覆盖。
cd "${APP_DIR:-/app}"
# shellcheck disable=SC1091
source "${APP_DIR:-/app}/.venv/bin/activate"

echo "=== [1/3] 代码测试 (pytest) ==="
python -m pytest -q

echo "=== [2/3] 前端构建 (tsc 类型检查 + vite 构建) ==="
(
  cd frontend
  npm run build
)

echo "=== [3/3] API 冒烟 (启动 uvicorn 并发起真实 HTTP 请求) ==="
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
cleanup() {
  kill "${SERVER_PID}" 2>/dev/null || true
  wait "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

python scripts/smoke_api.py

echo "=== verify 全部通过 ==="
