#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
INSTALL_SERVICE=1

if [[ ${1:-} == "--no-service" ]]; then
  INSTALL_SERVICE=0
elif [[ $# -ne 0 ]]; then
  echo "Использование: ./install.sh [--no-service]" >&2
  exit 2
fi

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

if [[ ! -f frontend/dist/index.html ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Нужен Node.js, чтобы собрать интерфейс: sudo apt install nodejs npm" >&2
    echo "Или положи уже собранный frontend/dist/ и запусти install.sh снова." >&2
    exit 1
  fi
  (cd frontend && npm ci && npm run build)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
  TOKEN=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))")
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET|" .env
  sed -i "s|^AGENT_TOKEN=.*|AGENT_TOKEN=$TOKEN|" .env
  chmod 600 .env
fi

set -a
source .env
set +a
: "${DJANGO_SECRET_KEY:?В server/.env не задан DJANGO_SECRET_KEY}"
: "${AGENT_NAME:?В server/.env не задан AGENT_NAME}"
: "${AGENT_TOKEN:?В server/.env не задан AGENT_TOKEN}"

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py create_agent "$AGENT_NAME" --token "$AGENT_TOKEN"

if [[ $INSTALL_SERVICE -eq 1 ]]; then
  USER_NAME="${SUDO_USER:-$(id -un)}"
  cat > fpga-server.service <<EOF
[Unit]
Description=FPGA remote testbed server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory="${ROOT}"
ExecStart="${ROOT}/run.sh"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  SUDO=()
  [[ $(id -u) -eq 0 ]] || SUDO=(sudo)
  "${SUDO[@]}" install -m 0644 fpga-server.service /etc/systemd/system/fpga-server.service
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable --now fpga-server
fi

echo "Сервер готов: http://<ip-этой-машины>:${PORT:-8000}"
echo "Конфиг: $ROOT/.env"
echo "Токен агента: $AGENT_TOKEN"
[[ $INSTALL_SERVICE -eq 1 ]] || echo "Запуск: $ROOT/run.sh"
