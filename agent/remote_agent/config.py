from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Допустимый диапазон длительности записи видео (секунды).
RECORD_DURATION_MIN: int = 1
RECORD_DURATION_MAX: int = 30


@dataclass(slots=True)
class AgentConfig:
    server_url: str
    token: str
    mode: str = "simulation"
    poll_interval: int = 5
    workspace: Path = Path("workspace")
    timeout_seconds: int = 300
    record_duration_sec: int = 15
    camera_device: str = "/dev/video0"
    gpio_chip: int = 0
    gpio_pins: tuple[int, ...] = (21, 20, 16, 12, 1, 7, 8, 25)
    openocd_command: str = "openocd"
    openocd_config: Path = Path("utils/board/max10.cfg")
    stream_fps: int = 8

    @classmethod
    def from_env(cls) -> "AgentConfig":
        mode = os.getenv("MODE", "simulation").strip().lower()
        if mode not in {"simulation", "hardware"}:
            raise ValueError("MODE должен быть simulation или hardware")

        pins = tuple(int(value.strip()) for value in os.getenv("GPIO_PINS", "21,20,16,12,1,7,8,25").split(","))
        if len(pins) != 8 or len(set(pins)) != 8 or any(pin < 0 or pin > 53 for pin in pins):
            raise ValueError("GPIO_PINS должен содержать восемь разных BCM-номеров")

        raw_duration = int(os.getenv("RECORD_DURATION_SECONDS", "15"))
        record_duration_sec = max(RECORD_DURATION_MIN, min(raw_duration, RECORD_DURATION_MAX))

        return cls(
            server_url=os.getenv("SERVER_URL", "http://127.0.0.1:8000").rstrip("/"),
            token=os.getenv("AGENT_TOKEN", ""),
            mode=mode,
            poll_interval=int(os.getenv("POLL_INTERVAL", "5")),
            workspace=Path(os.getenv("WORKSPACE", "workspace")),
            timeout_seconds=int(os.getenv("TIMEOUT_SECONDS", "300")),
            record_duration_sec=record_duration_sec,
            camera_device=os.getenv("CAMERA_DEVICE", "/dev/video0"),
            gpio_chip=int(os.getenv("GPIO_CHIP", "0")),
            gpio_pins=pins,
            openocd_command=os.getenv("OPENOCD_COMMAND", "openocd"),
            openocd_config=Path(os.getenv("OPENOCD_CONFIG", "utils/board/max10.cfg")),
            stream_fps=int(os.getenv("STREAM_FPS", "8")),
        )
