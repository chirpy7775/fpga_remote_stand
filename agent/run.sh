#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Сначала запусти ./install.sh" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "Нет файла .env. Скопируй .env.example в .env и пропиши URL сервера и токен." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
exec .venv/bin/python -m remote_agent "$@"
