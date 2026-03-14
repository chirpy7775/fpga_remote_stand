from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AgentConfig:
    server_url: str
    token: str
    poll_interval: int = 5
    workspace: Path = Path("workspace")
    timeout_seconds: int = 300
    run_once: bool = False

    @classmethod
    def from_env(cls) -> "AgentConfig":
        server_url = os.getenv("REMOTE_STAND_SERVER_URL", "http://127.0.0.1:8000")
        token = os.getenv("REMOTE_STAND_AGENT_TOKEN", "")
        poll_interval = int(os.getenv("REMOTE_STAND_POLL_INTERVAL", "5"))
        workspace = Path(os.getenv("REMOTE_STAND_WORKSPACE", "workspace"))
        timeout_seconds = int(os.getenv("REMOTE_STAND_TIMEOUT_SECONDS", "300"))
        return cls(
            server_url=server_url.rstrip("/"),
            token=token,
            poll_interval=poll_interval,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )
