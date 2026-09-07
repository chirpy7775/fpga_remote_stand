# Агент стенда

Забирает задачи с сервера, шьёт плату, дёргает пины и отдаёт видео.

## Переменные окружения

```bash
export REMOTE_STAND_SERVER_URL=http://192.168.2.34:8000
export REMOTE_STAND_AGENT_TOKEN=<TOKEN>
export REMOTE_STAND_POLL_INTERVAL=5
export REMOTE_STAND_WORKSPACE=./workspace
export REMOTE_STAND_TIMEOUT_SECONDS=300
export REMOTE_STAND_RECORD_DURATION_SECONDS=15
```

Можно положить их в `agent/.env` — агент читает его сам.

## Запуск

Разработка без платы (по умолчанию):

```bash
python -m remote_agent --stub-hardware
```

Реальный стенд на Raspberry Pi:

```bash
python -m remote_agent --real-hardware
```

## Режимы

| | `--stub-hardware` | `--real-hardware` |
|---|---|---|
| прошивка | `ProgrammerStub` | `RealProgrammer` — OpenOCD + USB-Blaster |
| пины | `StubGpio` — только в памяти | `RealGpio` — lgpio, BCM 21,20,16,12,1,7,8,25 |
| камера | `StubCamera` — рисованные кадры | `RealCamera` — V4L2 MJPEG с `/dev/video0` |

## Зависимости на Pi

```bash
sudo apt install openocd ffmpeg python3-lgpio
pip install -r requirements.txt
```

`lgpio` ставится из apt, поэтому venv нужен с `--system-site-packages`.
Пользователь должен быть в группах `gpio`, `video`, `plugdev`.

## Безопасность пинов

Линии стенда лежат входами (высокий импеданс), пока сценарий или сессия явно не
выставит уровень. После задачи и после сессии всё гасится в low и снова
отпускается. Это чтобы малина не спорила за пин с битстримом, который держит тот
же вывод выходом.

## Тесты

```bash
python -m unittest discover -s tests -t .
```
