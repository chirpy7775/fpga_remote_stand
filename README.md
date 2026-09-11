# Remote FPGA testbed

Сервер и агент — два независимых куска. Токен стенда придумываешь сам и вписываешь в оба `.env`.

## Оба на одной малине

```bash
git clone <этот-репозиторий>
cd fpga_remote_stand

# придумай строку-токен, например: my-lab-token
nano server/.env.example   # можно сразу после install

./server/install.sh
# открой server/.env и поставь:
#   AGENT_TOKEN_stand-1=my-lab-token

./agent/install.sh
# открой agent/.env и поставь:
#   REMOTE_STAND_SERVER_URL=http://127.0.0.1:8000
#   REMOTE_STAND_AGENT_TOKEN=my-lab-token

./server/run.sh          # в одном терминале
./agent/run.sh           # в другом
```

Браузер: `http://<ip-малины>:8000`

Автозапуск после ребута — если нужен, скопируй unit, который напечатал `install.sh`:

```bash
sudo cp server/fpga-server.service /etc/systemd/system/
sudo cp agent/fpga-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fpga-server fpga-agent
```

Не нужен автозапуск — unit не копируй. Убрать: `systemctl disable --now …` и удалить файл из `/etc/systemd/system/`.

## Сервер на компе, агент на малине

На компе:

```bash
./server/install.sh
# в server/.env: AGENT_TOKEN_stand-1=my-lab-token
./server/run.sh
```

На малине (клонируй репозиторий или скопируй каталог `agent/`):

```bash
./agent/install.sh
# в agent/.env:
#   REMOTE_STAND_SERVER_URL=http://192.168.2.34:8000
#   REMOTE_STAND_AGENT_TOKEN=my-lab-token
./agent/run.sh
```

IP в URL — тот, по которому малина видит комп. Токен должен совпасть с `AGENT_TOKEN_stand-1`.

## Что умеет

- асинхронная задача: `.svf` + `.txt` → видео с камеры;
- синхронная сессия: стрим, пины 1–8, заливка SVF;
- панель `/monitor` (нужен staff).

Пример прошивки: `server/examples/gpio_leds/`. Распиновка: `/docs/fpga`.

Разработка фронта на Vite (`npm run dev` в `server/frontend`) — отдельно, не часть установки.
