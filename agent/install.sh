#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
MODE_ARG=""
SERVER_ARG=""
TOKEN_ARG=""
INSTALL_SERVICE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE_ARG="${2:-}"; shift 2 ;;
    --server) SERVER_ARG="${2:-}"; shift 2 ;;
    --token) TOKEN_ARG="${2:-}"; shift 2 ;;
    --no-service) INSTALL_SERVICE=0; shift ;;
    *) echo "Использование: ./install.sh [--mode hardware|simulation] [--server URL] [--token TOKEN] [--no-service]" >&2; exit 2 ;;
  esac
done

if [[ ! -f .env ]]; then
  cp .env.example .env
  if [[ -f ../server/.env ]]; then
    set -a
    source ../server/.env
    set +a
    SERVER_ARG="${SERVER_ARG:-http://127.0.0.1:${PORT:-8000}}"
    TOKEN_ARG="${TOKEN_ARG:-${AGENT_TOKEN:-}}"
  fi
  chmod 600 .env
fi

[[ -z $MODE_ARG ]] || sed -i "s|^MODE=.*|MODE=$MODE_ARG|" .env
[[ -z $SERVER_ARG ]] || sed -i "s|^SERVER_URL=.*|SERVER_URL=$SERVER_ARG|" .env
[[ -z $TOKEN_ARG ]] || sed -i "s|^AGENT_TOKEN=.*|AGENT_TOKEN=$TOKEN_ARG|" .env

set -a
source .env
set +a
if [[ $MODE != "hardware" && $MODE != "simulation" ]]; then
  echo "MODE должен быть hardware или simulation" >&2
  exit 2
fi
: "${AGENT_TOKEN:?В agent/.env не задан AGENT_TOKEN}"

if [[ $MODE == "hardware" ]] && command -v apt-get >/dev/null 2>&1; then
  if [[ $(id -u) -eq 0 ]]; then
    apt-get update
    apt-get install -y python3-venv python3-lgpio openocd ffmpeg
  else
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-lgpio openocd ffmpeg
  fi
fi

python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt

if [[ $INSTALL_SERVICE -eq 1 ]]; then
  USER_NAME="${SUDO_USER:-$(id -un)}"
  cat > fpga-agent.service <<EOF
[Unit]
Description=FPGA remote testbed agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory="${ROOT}"
ExecStart="${ROOT}/run.sh"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  SUDO=()
  [[ $(id -u) -eq 0 ]] || SUDO=(sudo)
  if [[ $MODE == "hardware" ]]; then
    "${SUDO[@]}" usermod -aG gpio,video,plugdev "$USER_NAME"
  fi
  "${SUDO[@]}" install -m 0644 fpga-agent.service /etc/systemd/system/fpga-agent.service
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable --now fpga-agent
fi

echo "Агент готов (${MODE}), сервер ${SERVER_URL}"
echo "Конфиг: $ROOT/.env"
[[ $INSTALL_SERVICE -eq 1 ]] || echo "Запуск: $ROOT/run.sh"
