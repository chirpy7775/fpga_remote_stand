from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from .api import ServerClient
from .config import AgentConfig, LOG_BACKUP_COUNT, LOG_FILE, LOG_MAX_BYTES
from .env import load_env
from .hardware import Camera, GpioDriver, HardwareExecutor, Programmer, ProgrammerStub, StubCamera, StubGpio
from .hardware_real import RealCamera, RealGpio, RealProgrammer
from .logging_setup import setup_logging
from .worker import AgentWorker

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Агент удалённого стенда FPGA")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--stub-hardware",
        action="store_true",
        help="программатор, GPIO и камера — заглушки",
    )
    mode.add_argument(
        "--real-hardware",
        action="store_true",
        help="реальное железо: OpenOCD, lgpio, камера V4L2; иначе берётся REMOTE_STAND_REAL_HARDWARE из .env",
    )
    parser.add_argument(
        "--camera-device",
        default=None,
        help="устройство камеры для --real-hardware (по умолчанию из .env или /dev/video0)",
    )
    return parser


def resolve_real_hardware(args, config: AgentConfig) -> bool:
    if args.real_hardware:
        return True
    if args.stub_hardware:
        return False
    return config.real_hardware


def build_hardware(real_hardware: bool, camera_device: str, config: AgentConfig) -> tuple[Programmer, GpioDriver, Camera]:
    if not real_hardware:
        return ProgrammerStub(), StubGpio(), StubCamera()

    _check_real_prerequisites(camera_device)
    return (
        RealProgrammer(),
        RealGpio(),
        RealCamera(device=camera_device, workspace=config.workspace),
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
    setup_logging(log_file=LOG_FILE, max_bytes=LOG_MAX_BYTES, backup_count=LOG_BACKUP_COUNT)

    args = build_parser().parse_args()
    config = AgentConfig.from_env()
    if not config.token:
        logger.error("[AGENT] Не задан REMOTE_STAND_AGENT_TOKEN")
        return 2

    real_hardware = resolve_real_hardware(args, config)
    camera_device = args.camera_device or config.camera_device
    programmer, gpio, camera = build_hardware(real_hardware, camera_device, config)
    mode = "реальное железо" if real_hardware else "заглушки"
    logger.info("[AGENT] Режим: %s, сервер %s", mode, config.server_url)

    worker = AgentWorker(
        config=config,
        client=ServerClient(server_url=config.server_url, token=config.token),
        executor=HardwareExecutor(programmer=programmer, camera=camera, gpio=gpio),
        gpio=gpio,
        camera=camera,
        token=config.token,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
