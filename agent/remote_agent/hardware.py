from __future__ import annotations

import time
from pathlib import Path

from .models import ExecutionResult


class ProgrammerStub:
    def program(self, firmware_path: Path) -> list[str]:
        return [
            "[STUB] Programmer invoked.",
            f"[STUB] Firmware path: {firmware_path}",
            "[STUB] Real programming is not implemented",
        ]


class CameraStub:
    def __init__(self) -> None:
        self._video_path: Path | None = None

    def start_capture(self, video_path: Path) -> list[str]:
        self._video_path = video_path
        return [
            "[STUB] Camera capture started.",
            f"[STUB] Target video path: {video_path}",
        ]

    def stop_capture(self) -> list[str]:
        if self._video_path is not None:
            self._video_path.write_bytes(b"STUB VIDEO PLACEHOLDER\n")
        return ["[STUB] Camera capture stopped."]


class HardwareExecutor:
    def __init__(self, *, programmer: ProgrammerStub | None = None, camera: CameraStub | None = None) -> None:
        self.programmer = programmer or ProgrammerStub()
        self.camera = camera or CameraStub()

    def run(self, *, firmware_path: Path, workspace: Path, timeout_seconds: int) -> ExecutionResult:
        workspace.mkdir(parents=True, exist_ok=True)
        video_path = workspace / "result.mp4"
        log_lines: list[str] = []
        started_at = time.monotonic()

        try:
            log_lines.extend(self.camera.start_capture(video_path))
            time.sleep(min(1.0, timeout_seconds))

            if time.monotonic() - started_at > timeout_seconds:
                raise TimeoutError("Execution timed out before programming started.")

            log_lines.extend(self.programmer.program(firmware_path))
            time.sleep(min(1.0, timeout_seconds))

            if time.monotonic() - started_at > timeout_seconds:
                raise TimeoutError("Execution timed out during programming.")

            log_lines.append("[STUB] Execution finished successfully.")
            status = "completed"
            error_message = ""
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            log_lines.append(f"[STUB] Execution failed: {exc}")
        finally:
            log_lines.extend(self.camera.stop_capture())

        return ExecutionResult(
            status=status,
            execution_log="\n".join(log_lines),
            video_path=video_path,
            error_message=error_message,
        )
