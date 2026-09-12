from __future__ import annotations

import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .api import ServerClient
from .config import AgentConfig
from .env import load_env
from .hardware import Camera, GpioDriver, HardwareExecutor, Programmer, ProgrammerStub, StubCamera, StubGpio
from .hardware_real import RealCamera, RealGpio, RealProgrammer
from .worker import AgentWorker

logger = logging.getLogger(__name__)


def build_hardware(config: AgentConfig) -> tuple[Programmer, GpioDriver, Camera]:
    if config.mode == "simulation":
        return ProgrammerStub(), StubGpio(), StubCamera()

    _check_real_prerequisites(config.camera_device)
    return (
        RealProgrammer(config_path=config.openocd_config, openocd_cmd=config.openocd_command),
        RealGpio(chip=config.gpio_chip, pins=config.gpio_pins),
        RealCamera(device=config.camera_device, workspace=config.workspace),
    )


def _check_real_prerequisites(camera_device: str) -> None:
    """Ругаемся в лог заранее, а не посреди чужой задачи."""
    for binary in ("openocd", "ffmpeg"):
        if shutil.which(binary) is None:
            logger.warning("[AGENT] %s не найден в PATH — соответствующий этап упадёт", binary)
    if not Path(camera_device).exists():
        logger.warning("[AGENT] Камера %s не найдена — видео не будет записано", camera_device)
    try:
        import lgpio  # noqa: F401
    except ImportError:
        logger.warning("[AGENT] Модуль lgpio недоступен — управление пинами не заработает")


def main() -> int:
    load_env()
    log_path = Path(os.getenv("LOG_FILE", "logs/agent.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )],
    )

    try:
        config = AgentConfig.from_env()
    except (TypeError, ValueError) as exc:
        logger.error("[AGENT] Ошибка в .env: %s", exc)
        return 2
    if not config.token:
        logger.error("[AGENT] Не задан AGENT_TOKEN")
        return 2

    programmer, gpio, camera = build_hardware(config)
    logger.info("[AGENT] Режим: %s, сервер %s", config.mode, config.server_url)

    worker = AgentWorker(
        config=config,
        client=ServerClient(server_url=config.server_url, token=config.token, gpio_pins=config.gpio_pins),
        executor=HardwareExecutor(programmer=programmer, camera=camera, gpio=gpio),
        gpio=gpio,
        camera=camera,
        token=config.token,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
