# Agent

Минимальный исполнитель задач.

## Переменные окружения

```bash
export REMOTE_STAND_SERVER_URL=http://127.0.0.1:8000
export REMOTE_STAND_AGENT_TOKEN=<TOKEN>
export REMOTE_STAND_POLL_INTERVAL=5
export REMOTE_STAND_WORKSPACE=./workspace
```

## Запуск

```bash
python -m remote_agent
```

Однократный проход:

```bash
python -m remote_agent --once
```

## Где менять заглушки на реальную интеграцию

Файл `remote_agent/hardware.py`.
