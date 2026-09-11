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
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py sync_agents

read -r HOST PORT <<EOF
$(.venv/bin/python -c "from remote_stand.env import load_env; import os; load_env(); print(os.getenv('HOST', '0.0.0.0').strip(), os.getenv('PORT', '8000').strip())")
EOF

exec .venv/bin/python manage.py runserver "${HOST}:${PORT}" --noreload
