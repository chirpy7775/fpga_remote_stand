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

Для разработки без платы:

```bash
python -m remote_agent --stub-hardware
```

Для запуска с реальным железом:

```bash
python -m remote_agent
```

## Что делает `--stub-hardware`

В этом режиме агент использует:

- `ProgrammerStub`
- `CameraStub`

Это позволяет обрабатывать задачи без FPGA-платы, OpenOCD и физической камеры.

## Где менять интеграцию с железом

Файл `remote_agent/hardware.py`.
