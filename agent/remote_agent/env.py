from __future__ import annotations

import os
from pathlib import Path


def load_env() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    candidates = [base_dir / ".env", base_dir.parent / ".env"]

    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
