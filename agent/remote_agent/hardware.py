from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol

from .frames import HEIGHT, WIDTH, render_stub_frame
from .hardware_real import RealCamera, RealProgrammer
from .lite_lang import PinCommand, WriteFrameCommand, parse_instruction
from .models import ExecutionResult

logger = logging.getLogger(__name__)


class Programmer(Protocol):
    def program(self, firmware_path: Path) -> list[str]:
        ...


class GpioDriver(Protocol):
    def set_pin(self, pin: int, high: bool) -> str:
        ...

    def snapshot(self) -> list[bool]:
        ...


class Camera(Protocol):
    def render_frame(self, pins: list[bool], tick: int) -> bytes:
        ...


class ProgrammerStub:
    def program(self, firmware_path: Path) -> list[str]:
        time.sleep(0.2)
        return [
            "[STUB] Programmer invoked.",
            f"[STUB] Firmware path: {firmware_path}",
            "[STUB] Прошивка успешно загружена.",
        ]


class StubGpio:
    def __init__(self) -> None:
        self._pins = [False] * 8

    def set_pin(self, pin: int, high: bool) -> str:
        if pin < 1 or pin > 8:
            raise ValueError(f"Пин {pin} вне диапазона 1..8")
        self._pins[pin - 1] = high
        level = "high" if high else "low"
        logger.info("GPIO stub pin=%s %s", pin, level)
        return f"[GPIO] pin {pin} {level}"

    def snapshot(self) -> list[bool]:
        return list(self._pins)


class CameraStub:
    def render_frame(self, pins: list[bool], tick: int) -> bytes:
        return render_stub_frame(pins, tick)


class HardwareExecutor:
    def __init__(
        self,
        *,
        programmer: Programmer | None = None,
        camera: Camera | None = None,
        gpio: GpioDriver | None = None,
        fps: int = 10,
    ) -> None:
        self.programmer = programmer or ProgrammerStub()
        self.camera = camera or CameraStub()
        self.gpio = gpio or StubGpio()
        self.fps = fps

    def run(
        self,
        *,
        firmware_path: Path,
        instruction_text: str,
        workspace: Path,
        timeout_seconds: int,
        record_duration_sec: float = 15.0,
    ) -> ExecutionResult:
        workspace.mkdir(parents=True, exist_ok=True)
        video_path = workspace / "result.mp4"
        log_lines: list[str] = []
        started_at = time.monotonic()

        log_lines.append("=== Начало прошивки FPGA ===")
        prog_log = self.programmer.program(firmware_path)
        log_lines.extend(prog_log)
        programming_ok = any("успешно" in line for line in prog_log) and not any(
            "Ошибка" in line for line in prog_log
        )
        if not programming_ok:
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log_lines),
                video_path=None,
                error_message="Programming failed",
            )

        try:
            commands = parse_instruction(instruction_text)
        except ValueError as exc:
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log_lines + [str(exc)]),
                video_path=None,
                error_message=str(exc),
            )

        frames: list[bytes] = []
        tick = 0
        log_lines.append("=== Выполнение инструкции ===")
        for command in commands:
            if time.monotonic() - started_at >= timeout_seconds:
                log_lines.append("Таймаут во время сценария.")
                return ExecutionResult(
                    status="error",
                    execution_log="\n".join(log_lines),
                    video_path=None,
                    error_message="Timeout during instruction",
                )
            if isinstance(command, PinCommand):
                log_lines.append(self.gpio.set_pin(command.pin, command.state == "high"))
            elif isinstance(command, WriteFrameCommand):
                for _ in range(command.frames):
                    frames.append(self.camera.render_frame(self.gpio.snapshot(), tick))
                    tick += 1
                    time.sleep(max(0.0, 1.0 / self.fps / 4))

        if not frames:
            frames.append(self.camera.render_frame(self.gpio.snapshot(), tick))

        log_lines.extend(write_stub_video(video_path, frames, fps=self.fps))
        ok = video_path.exists() and video_path.stat().st_size > 0
        return ExecutionResult(
            status="completed" if ok else "error",
            execution_log="\n".join(log_lines),
            video_path=video_path if ok else None,
            error_message="" if ok else "Видеофайл не создан",
        )


def write_stub_video(video_path: Path, frames: list[bytes], fps: int = 10) -> list[str]:
    log: list[str] = [f"[STUB] Сборка видео из {len(frames)} кадров."]
    if not frames:
        return log + ["[STUB] Нет кадров."]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, frame in enumerate(frames):
            (tmp_dir / f"frame_{index:04d}.png").write_bytes(frame)
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(tmp_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and video_path.exists():
                log.append("[STUB] Видео собрано через ffmpeg.")
                return log
            log.append(f"[STUB] ffmpeg не смог собрать видео (code={result.returncode}).")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.append(f"[STUB] ffmpeg недоступен: {exc}")

    video_path.write_bytes(frames[-1])
    log.append("[STUB] Записан PNG-кадр как fallback (ffmpeg не найден).")
    return log


__all__ = [
    "CameraStub",
    "HardwareExecutor",
    "ProgrammerStub",
    "RealCamera",
    "RealProgrammer",
    "StubGpio",
]
