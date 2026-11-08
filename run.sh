#!/usr/bin/env bash
# 知天命 一键启动
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "首次运行：创建虚拟环境并安装依赖…"
  uv venv --python 3.12 .venv
  . .venv/bin/activate
  uv pip install -r requirements.txt
else
  . .venv/bin/activate
fi

echo "启动 知天命 · http://127.0.0.1:8000"
exec uvicorn backend.main:app --host 127.0.0.1 --port 8000 "$@"
