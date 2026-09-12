#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Сначала запусти ./install.sh" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "Нет файла .env. Скопируй .env.example в .env и пропиши токены." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
set -a
source .env
set +a

.venv/bin/python manage.py migrate --noinput
: "${AGENT_NAME:?В server/.env не задан AGENT_NAME}"
: "${AGENT_TOKEN:?В server/.env не задан AGENT_TOKEN}"
.venv/bin/python manage.py create_agent "$AGENT_NAME" --token "$AGENT_TOKEN" >/dev/null

exec .venv/bin/python manage.py runserver "${HOST:-0.0.0.0}:${PORT:-8000}" --noreload
