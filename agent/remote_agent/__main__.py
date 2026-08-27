from __future__ import annotations

import argparse

from .api import ServerClient
from .config import AgentConfig, LOG_BACKUP_COUNT, LOG_FILE, LOG_MAX_BYTES
from .env import load_env
from .hardware import CameraStub, HardwareExecutor, ProgrammerStub, RealCamera, RealProgrammer, StubGpio
from .logging_setup import setup_logging
from .worker import AgentWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote stand agent")
    parser.add_argument(
        "--stub-hardware",
        action="store_true",
        help="use stub programmer, gpio and camera (default)",
    )
    parser.add_argument(
        "--real-hardware",
        action="store_true",
        help="use OpenOCD programmer and V4L2 camera",
    )
    return parser


def main() -> int:
    load_env()
    setup_logging(
        log_file=LOG_FILE,
        max_bytes=LOG_MAX_BYTES,
        backup_count=LOG_BACKUP_COUNT,
    )

    parser = build_parser()
    args = parser.parse_args()
    config = AgentConfig.from_env()
    client = ServerClient(server_url=config.server_url, token=config.token)
    gpio = StubGpio()

    if args.real_hardware:
        executor = HardwareExecutor(
            programmer=RealProgrammer(),
            camera=CameraStub(),
            gpio=gpio,
        )
        _ = RealCamera
    else:
        executor = HardwareExecutor(
            programmer=ProgrammerStub(),
            camera=CameraStub(),
            gpio=gpio,
        )

    worker = AgentWorker(
        config=config,
        client=client,
        executor=executor,
        gpio=gpio,
        token=config.token,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
