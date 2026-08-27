# Remote FPGA testbed

Сервер (Django) + агенты на Raspberry Pi. Сейчас железо в stub-режиме: можно разрабатывать без платы.

## Что умеет этот срез

- асинхронная задача: `.svf` + `.txt` lite_lang → очередь конкретного стенда → видео-результат;
- синхронная сессия: занять стенд, JPEG-стрим, кнопки пинов 1–8, заливка SVF;
- несколько агентов на один сервер, heartbeat, exclusive lock;
- UI как у CloudBurner (React + Tailwind);
- гостевая отправка заявок без аккаунта (история в cookie браузера).

## Запуск

Терминал 1 — сервер:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py create_agent stand-1
python manage.py create_agent stand-2
python manage.py runserver 127.0.0.1:8000
```

`:8000` — только API, админка и агенты. Интерфейс — на `:5173`.

Токены агентов выведет `create_agent`. Подставьте в `.env` или в окружение.

Терминал 2 — фронт:

```bash
cd server/frontend
npm install
npm run dev
```

Открыть http://127.0.0.1:5173

Терминал 3/4 — агенты (stub):

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
REMOTE_STAND_SERVER_URL=http://127.0.0.1:8000 REMOTE_STAND_AGENT_TOKEN=<token-stand-1> python -m remote_agent --stub-hardware
```

Второй агент — с токеном stand-2.

Примеры файлов: `server/examples/blink.svf`, `server/examples/blink_gpio.txt`.

## Инструкция GPIO

```
pin 1 high
write_frame 10
pin 1 low
write_frame 10
```

Пины 1–8. `write_frame` — задержка в кадрах stub-камеры.

Реальное железо на Pi — следующий этап (`--real-hardware`, OpenOCD, lgpio, V4L2).
