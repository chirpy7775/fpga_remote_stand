#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

if command -v apt-get >/dev/null 2>&1; then
  if [[ $(id -u) -eq 0 ]]; then
    apt-get update
    apt-get install -y python3-venv python3-lgpio openocd ffmpeg
  else
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-lgpio openocd ffmpeg
  fi
fi

python3 -m venv --system-site-packages .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан $ROOT/.env — пропиши URL сервера и тот же токен, что в server/.env"
fi

USER_NAME="$(id -un)"
cat > fpga-agent.service <<EOF
[Unit]
Description=FPGA remote stand agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${ROOT}
ExecStart=${ROOT}/run.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chmod +x run.sh install.sh

echo
echo "Агент готов."
echo "  Конфиг: $ROOT/.env"
echo "  Запуск: $ROOT/run.sh"
echo
echo "Автозапуск (по желанию):"
echo "  sudo cp $ROOT/fpga-agent.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now fpga-agent"
echo "Убрать автозапуск:"
echo "  sudo systemctl disable --now fpga-agent"
echo "  sudo rm /etc/systemd/system/fpga-agent.service"
echo
echo "На Raspberry Pi пользователь должен быть в группах gpio, video, plugdev:"
echo "  sudo usermod -aG gpio,video,plugdev ${USER_NAME}"
echo "  (потом перелогиниться)"
