#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/.runtime/debug/live-debug-20261023T013447Z/runtime"
if [ ! -x "$ROOT/.venv/bin/python" ] || [ ! -d "$RUNTIME" ]; then
  echo "缺少现有 Python 环境或 Debug Runtime；未创建资料、未启动服务。" >&2
  exit 1
fi
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
exec "$ROOT/.venv/bin/python" -B -m cli.debug_workspace \
  --runtime-dir "$RUNTIME" --port 8013 \
  --allow-paid-actions --replace-existing
