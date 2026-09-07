from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .frames import render_stub_frame
from .lite_lang import InstructionError, PinCommand, WriteFrameCommand, parse_instruction
from .models import ExecutionResult

logger = logging.getLogger(__name__)

PIN_COUNT = 8
DEFAULT_FPS = 10


@dataclass(slots=True)
class ProgramResult:
    """Итог прошивки. `ok` определяет сам программатор, без разбора текста снаружи."""

    ok: bool
    log: list[str] = field(default_factory=list)


class Programmer(Protocol):
    def program(self, firmware_path: Path) -> ProgramResult: ...


class GpioDriver(Protocol):
    def engage(self) -> None:
        """
        Взять все восемь линий под управление и выставить low.

        Нужно вызывать перед сценарием и в начале сессии: в покое линии
        отпущены, а плата подтягивает их вверх, поэтому без явного захвата
        неуправляемый пин выглядел бы как high.
        """
        ...

    def set_pin(self, pin: int, high: bool) -> str: ...

    def snapshot(self) -> list[bool]: ...

    def release(self) -> None:
        """Отпустить линии в высокий импеданс. Вызывается после задачи и сессии."""
        ...


class Camera(Protocol):
    fps: int

    def start_recording(self) -> list[str]: ...

    def hold_frames(self, frames: int, pins: list[bool]) -> None: ...

    def stop_recording(self, video_path: Path) -> list[str]: ...

    def live_frame(self, pins: list[bool]) -> bytes | None: ...

    def close(self) -> None: ...


class ProgrammerStub:
    def program(self, firmware_path: Path) -> ProgramResult:
        time.sleep(0.2)
        return ProgramResult(
            ok=True,
            log=[
                "[STUB] Программатор вызван.",
                f"[STUB] Файл прошивки: {firmware_path}",
                "[STUB] Прошивка загружена.",
            ],
        )


class StubGpio:
    def __init__(self) -> None:
        self._pins = [False] * PIN_COUNT

    def engage(self) -> None:
        self._pins = [False] * PIN_COUNT

    def set_pin(self, pin: int, high: bool) -> str:
        if pin < 1 or pin > PIN_COUNT:
            raise ValueError(f"Пин {pin} вне диапазона 1..{PIN_COUNT}")
        self._pins[pin - 1] = high
        level = "high" if high else "low"
        logger.info("GPIO stub pin=%s %s", pin, level)
        return f"[GPIO] pin {pin} {level}"

    def snapshot(self) -> list[bool]:
        return list(self._pins)

    def release(self) -> None:
        self._pins = [False] * PIN_COUNT


class StubCamera:
    """Рисует синтетические кадры: и в запись, и в живой стрим."""

    def __init__(self, fps: int = DEFAULT_FPS) -> None:
        self.fps = fps
        self._tick = 0
        self._frames: list[bytes] = []

    def start_recording(self) -> list[str]:
        self._frames = []
        return ["[STUB] Запись кадров начата."]

    def hold_frames(self, frames: int, pins: list[bool]) -> None:
        for _ in range(frames):
            self._frames.append(render_stub_frame(pins, self._tick))
            self._tick += 1

    def stop_recording(self, video_path: Path) -> list[str]:
        frames, self._frames = self._frames, []
        return _write_video_from_pngs(video_path, frames, fps=self.fps)

    def live_frame(self, pins: list[bool]) -> bytes | None:
        self._tick += 1
        return render_stub_frame(pins, self._tick)

    def close(self) -> None:
        self._frames = []


@dataclass(slots=True)
class _Playback:
    """Итог проигрывания сценария."""

    log: list[str] = field(default_factory=list)
    frames: int = 0
    timed_out: bool = False


class HardwareExecutor:
    """Прошивает плату, отыгрывает сценарий и отдаёт видео результата."""

    def __init__(
        self,
        *,
        programmer: Programmer | None = None,
        camera: Camera | None = None,
        gpio: GpioDriver | None = None,
    ) -> None:
        self.programmer = programmer or ProgrammerStub()
        self.camera = camera or StubCamera()
        self.gpio = gpio or StubGpio()

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
        log: list[str] = []
        deadline = time.monotonic() + timeout_seconds

        # Сценарий разбираем до прошивки: незачем трогать плату из-за опечатки в скрипте.
        try:
            commands = parse_instruction(instruction_text)
        except InstructionError as exc:
            return ExecutionResult(status="error", execution_log=str(exc), error_message=str(exc))

        log.append("=== Прошивка ===")
        programming = self.programmer.program(firmware_path)
        log.extend(programming.log)
        if not programming.ok:
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log),
                error_message="Прошивка не удалась",
            )

        log.append("=== Сценарий ===")
        try:
            play = self._play(commands, deadline, record_duration_sec)
            log.extend(play.log)
            # Линии снимаем сразу после сценария: перекодирование видео может
            # занять десятки секунд, и всё это время держать плату под
            # напряжением незачем. release() идемпотентен, finally ниже —
            # страховка на случай исключения.
            self.gpio.release()
            log.extend(self.camera.stop_recording(video_path))
        finally:
            self.gpio.release()

        video = video_path if video_path.exists() and video_path.stat().st_size > 0 else None
        if play.timed_out:
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log),
                video_path=video,
                error_message="Превышен лимит времени выполнения",
            )
        if video is None:
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log),
                error_message="Видео не записано",
            )
        return ExecutionResult(status="completed", execution_log="\n".join(log), video_path=video)

    def _play(
        self,
        commands: list[PinCommand | WriteFrameCommand],
        deadline: float,
        record_duration_sec: float,
    ) -> "_Playback":
        # Забираем все линии в low, чтобы кадры показывали ровно то, что задаёт
        # сценарий, а не подтяжки платы на неуправляемых пинах.
        self.gpio.engage()
        play = _Playback(log=self.camera.start_recording())

        def hold(frames: int) -> bool:
            """Снимает не больше, чем осталось до дедлайна. False — время вышло."""
            budget = max(0.0, deadline - time.monotonic())
            allowed = min(frames, int(budget * self.camera.fps))
            if allowed <= 0:
                play.timed_out = True
                return False
            self.camera.hold_frames(allowed, self.gpio.snapshot())
            play.frames += allowed
            return True

        for command in commands:
            if time.monotonic() >= deadline:
                play.timed_out = True
                break
            if isinstance(command, PinCommand):
                play.log.append(self.gpio.set_pin(command.pin, command.state == "high"))
            elif not hold(command.frames):
                break

        if play.timed_out:
            play.log.append("Сценарий прерван: истёк лимит времени.")
        elif play.frames == 0:
            # В сценарии не было write_frame — снимаем плату дефолтную длительность.
            play.log.append(f"В сценарии нет write_frame, записываю {record_duration_sec:g} с.")
            if not hold(max(1, int(record_duration_sec * self.camera.fps))):
                play.log.append("Сценарий прерван: истёк лимит времени.")

        play.log.append(f"Кадров записано: {play.frames} (~{play.frames / self.camera.fps:.1f} с).")
        return play


def _write_video_from_pngs(video_path: Path, frames: list[bytes], fps: int) -> list[str]:
    """Собирает mp4 из PNG-кадров заглушки."""
    if not frames:
        return ["[STUB] Нет кадров для видео."]

    log = [f"[STUB] Сборка видео из {len(frames)} кадров."]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, frame in enumerate(frames):
            (tmp_dir / f"frame_{index:04d}.png").write_bytes(frame)
        command = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(tmp_dir / "frame_%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(video_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and video_path.exists():
                return log + ["[STUB] Видео собрано."]
            log.append(f"[STUB] ffmpeg вернул код {result.returncode}.")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.append(f"[STUB] ffmpeg недоступен: {exc}")

    video_path.write_bytes(frames[-1])
    return log + ["[STUB] Записан последний кадр как PNG (без ffmpeg)."]


__all__ = [
    "Camera",
    "DEFAULT_FPS",
    "GpioDriver",
    "HardwareExecutor",
    "PIN_COUNT",
    "ProgramResult",
    "Programmer",
    "ProgrammerStub",
    "StubCamera",
    "StubGpio",
]
