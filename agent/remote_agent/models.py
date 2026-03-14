from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RemoteJob:
    id: str
    status: str
    original_filename: str
    download_url: str
    result_url: str
    detail_url: str
    deadline_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "RemoteJob":
        return cls(
            id=payload["id"],
            status=payload["status"],
            original_filename=payload["original_filename"],
            download_url=payload["download_url"],
            result_url=payload["result_url"],
            detail_url=payload["detail_url"],
            deadline_at=payload.get("deadline_at"),
        )


@dataclass(slots=True)
class ExecutionResult:
    status: str
    execution_log: str
    video_path: Path | None = None
    error_message: str = ""
