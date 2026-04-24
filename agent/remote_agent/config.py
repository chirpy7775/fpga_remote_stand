from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Допустимый диапазон длительности записи видео (секунды).
# Чтобы изменить границы — правьте только эти две константы.
RECORD_DURATION_MIN: int = 1
RECORD_DURATION_MAX: int = 30

# Настройки логирования с ротацией по размеру файла.
# LOG_FILE         — путь к лог-файлу (относительный или абсолютный).
# LOG_MAX_BYTES    — максимальный размер одного файла лога (байт).
# LOG_BACKUP_COUNT — сколько архивных файлов хранить (.log.1, .log.2, ...).
LOG_FILE: str = "agent.log"
LOG_MAX_BYTES: int = 10 * 1024 * 1024   # 10 МБ
LOG_BACKUP_COUNT: int = 5

@dataclass(slots=True)
class AgentConfig:
    server_url: str
    token: str
    poll_interval: int = 5
    workspace: Path = Path("workspace")
    timeout_seconds: int = 300
    record_duration_sec: int = 15

    @classmethod
    def from_env(cls) -> "AgentConfig":
        server_url = os.getenv("REMOTE_STAND_SERVER_URL", "http://127.0.0.1:8000")
        token = os.getenv("REMOTE_STAND_AGENT_TOKEN", "")
        poll_interval = int(os.getenv("REMOTE_STAND_POLL_INTERVAL", "5"))
        workspace = Path(os.getenv("REMOTE_STAND_WORKSPACE", "workspace"))
        timeout_seconds = int(os.getenv("REMOTE_STAND_TIMEOUT_SECONDS", "300"))

        raw_duration = int(os.getenv("REMOTE_STAND_RECORD_DURATION_SECONDS", "15"))
        record_duration_sec = max(RECORD_DURATION_MIN, min(raw_duration, RECORD_DURATION_MAX))

        return cls(
            server_url=server_url.rstrip("/"),
            token=token,
            poll_interval=poll_interval,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            record_duration_sec=record_duration_sec,
        )
