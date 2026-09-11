#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f frontend/dist/index.html ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Нужен Node.js, чтобы собрать интерфейс: sudo apt install nodejs npm" >&2
    echo "Или положи уже собранный frontend/dist/ и запусти install.sh снова." >&2
    exit 1
  fi
  (cd frontend && npm install && npm run build)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан $ROOT/.env — пропиши свой AGENT_TOKEN_stand-1=..."
fi

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py sync_agents

USER_NAME="$(id -un)"
cat > fpga-server.service <<EOF
[Unit]
Description=FPGA remote stand server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${ROOT}
ExecStart=${ROOT}/run.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

chmod +x run.sh install.sh

echo
echo "Сервер готов."
echo "  Конфиг:  $ROOT/.env"
echo "  Запуск:  $ROOT/run.sh"
echo "  Браузер: http://<ip-этой-машины>:8000"
echo
echo "Автозапуск (по желанию):"
echo "  sudo cp $ROOT/fpga-server.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now fpga-server"
echo "Убрать автозапуск:"
echo "  sudo systemctl disable --now fpga-server"
echo "  sudo rm /etc/systemd/system/fpga-server.service"
