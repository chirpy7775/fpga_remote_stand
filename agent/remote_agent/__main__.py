from __future__ import annotations

import argparse

from .api import ServerClient
from .config import AgentConfig
from .env import load_env
from .hardware import CameraStub, HardwareExecutor, ProgrammerStub
from .worker import AgentWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote stand agent")
    parser.add_argument(
        "--stub-hardware",
        action="store_true",
        help="use stub programmer and camera for development without FPGA board",
    )
    return parser


def main() -> int:
    load_env()
    parser = build_parser()
    args = parser.parse_args()

    config = AgentConfig.from_env()

    client = ServerClient(server_url=config.server_url, token=config.token)
    if args.stub_hardware:
        executor = HardwareExecutor(
            programmer=ProgrammerStub(),
            camera=CameraStub(),
        )
    else:
        executor = HardwareExecutor()
    worker = AgentWorker(config=config, client=client, executor=executor)
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
