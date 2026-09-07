# Remote FPGA testbed

Сервер (Django) + агенты на Raspberry Pi, которые шьют настоящую плату
Terasic DE10-Lite и снимают её на камеру.

## Что умеет

- **асинхронная задача**: `.svf` + `.txt` lite_lang → очередь конкретного стенда → видео результата;
- **синхронная сессия**: занять стенд, живой JPEG-стрим с камеры, кнопки пинов 1–8, заливка SVF;
- **реальное железо**: OpenOCD + USB-Blaster, GPIO через lgpio, запись V4L2 → H.264;
- **stub-режим**: то же самое без платы, для разработки;
- несколько агентов на один сервер, heartbeat, эксклюзивная блокировка стенда;
- гостевая отправка заявок без аккаунта (история в cookie браузера);
- **панель мониторинга** `/monitor` для персонала: кто занял стенд, что выполняется,
  кто и что загружал, логи и видео заявок.

## Запуск

Терминал 1 — сервер:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py create_agent stand-1
python manage.py createsuperuser          # нужен для /monitor
python manage.py runserver 0.0.0.0:8000   # 0.0.0.0 — чтобы дотянулся агент с Pi
```

Если сервер слушает не только localhost, перечислите адреса:

```bash
export DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.2.34
export DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173,http://192.168.2.34:5173
```

`:8000` — только API, админка и агенты. Интерфейс — на `:5173`.
Токены агентов выведет `create_agent`.

Терминал 2 — фронт:

```bash
cd server/frontend
npm install
npm run dev
```

Открыть http://127.0.0.1:5173

Терминал 3 — агент без платы:

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
REMOTE_STAND_SERVER_URL=http://127.0.0.1:8000 \
REMOTE_STAND_AGENT_TOKEN=<token-stand-1> \
python -m remote_agent --stub-hardware
```

## Реальный стенд на Raspberry Pi

Подробности — в [`agent/README.md`](agent/README.md). Коротко:

```bash
sudo apt install openocd ffmpeg python3-lgpio
rsync -a agent/ user@<pi>:/home/user/fpga-stand/agent/
ssh user@<pi>
cd /home/user/fpga-stand
python3 -m venv --system-site-packages .venv   # lgpio берём из apt
.venv/bin/pip install -r agent/requirements.txt
```

Настройки — в `agent/.env`, автозапуск — юнитом `agent/utils/fpga-agent.service`:

```bash
sudo cp agent/utils/fpga-agent.service /etc/systemd/system/
sudo systemctl enable --now fpga-agent
journalctl -u fpga-agent -f
```

## Инструкция GPIO (lite_lang)

```
pin 1 high
write_frame 10
pin 1 low
write_frame 10
```

Пины 1–8. `write_frame N` — выдержка длиной `N / 10` секунды: столько времени
камера снимает плату в текущем состоянии пинов.

Готовый пример под DE10-Lite: [`server/examples/gpio_leds/`](server/examples/gpio_leds/)
(проект Quartus, скрипт `gpio_leds.txt`, собранный `gpio_led_test.svf`).
Распиновка и предупреждения по железу — на странице `/docs/fpga`.

## Тесты

```bash
cd server && python manage.py test jobs      # 44 теста
cd agent  && python -m unittest discover -s tests -t .   # 26 тестов
```

Проверки на живом стенде (нужен запущенный сервер, фронт и агент):

```bash
cd server
pip install -r requirements-dev.txt
python scripts/check_sync_session.py   # сессия: стрим, пины, прошивка
python scripts/check_ui.py             # скриншоты страниц + права на /monitor
```
