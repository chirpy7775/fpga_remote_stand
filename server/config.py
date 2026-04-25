from __future__ import annotations

import os


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ALLOW_ANON_JOB_SUBMISSION = env_bool("ALLOW_ANON_JOB_SUBMISSION", True)
