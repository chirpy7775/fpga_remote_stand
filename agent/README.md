# Агент стенда

Ставится своим `install.sh`. Токен — тот же, что в `server/.env`.

```bash
./install.sh
# правь .env: URL сервера и REMOTE_STAND_AGENT_TOKEN
./run.sh
```

Автозапуск: скопируй `fpga-agent.service`, который написал `install.sh`, в `/etc/systemd/system/` и `enable --now`.

## Переменные в `.env`

```bash
REMOTE_STAND_SERVER_URL=http://192.168.2.34:8000
REMOTE_STAND_AGENT_TOKEN=<тот же токен, что AGENT_TOKEN_stand-1 на сервере>
REMOTE_STAND_REAL_HARDWARE=1
REMOTE_STAND_POLL_INTERVAL=5
REMOTE_STAND_CAMERA_DEVICE=/dev/video0
```

`REMOTE_STAND_REAL_HARDWARE=0` — заглушки (разработка без платы). Флаги `--real-hardware` / `--stub-hardware` перекрывают `.env`.

## Режимы

| | заглушки | реальное железо |
|---|---|---|
| прошивка | `ProgrammerStub` | `RealProgrammer` — OpenOCD + USB-Blaster |
| пины | `StubGpio` — только в памяти | `RealGpio` — lgpio, BCM 21,20,16,12,1,7,8,25 |
| камера | `StubCamera` — рисованные кадры | `RealCamera` — V4L2 MJPEG с `/dev/video0` |

`lgpio` ставится из apt, поэтому venv создаётся с `--system-site-packages`.
На Pi пользователь должен быть в группах `gpio`, `video`, `plugdev`.

## Безопасность пинов

Линии стенда лежат входами (высокий импеданс), пока сценарий или сессия явно не
выставит уровень. После задачи и после сессии всё гасится в low и снова
отпускается. Это чтобы малина не спорила за пин с битстримом, который держит тот
же вывод выходом.

## Тесты

```bash
python -m unittest discover -s tests -t .
```
