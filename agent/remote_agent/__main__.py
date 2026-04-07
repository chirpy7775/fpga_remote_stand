from __future__ import annotations

import argparse

from .api import ServerClient
from .config import AgentConfig
from .env import load_env
from .hardware import HardwareExecutor
from .worker import AgentWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote stand agent")
    parser.add_argument("--once", action="store_true", help="claim and process at most one job")
    return parser


def main() -> int:
    load_env()
    parser = build_parser()
    args = parser.parse_args()

    config = AgentConfig.from_env()
    config.run_once = args.once

    client = ServerClient(server_url=config.server_url, token=config.token)
    executor = HardwareExecutor()
    worker = AgentWorker(config=config, client=client, executor=executor)
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
