from __future__ import annotations

import time
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .models import ExecutionResult

if TYPE_CHECKING:
    import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None
    print("Предупреждение: OpenCV (cv2) не установлен. RealCamera будет работать как заглушка.")


class ProgrammerStub:
    def program(self, firmware_path: Path) -> list[str]:
        return [
            "[STUB] Programmer invoked.",
            f"[STUB] Firmware path: {firmware_path}",
            "[STUB] Прошивка успешно загружена.",
        ]


class RealProgrammer:
    def __init__(self, config_path: Path | None = None, openocd_cmd: str = "openocd"):
        if config_path is None:
            current_dir = Path(__file__).parent
            config_path = current_dir.parent / "utils" / "board" / "max10.cfg"
        self.config_path = Path(config_path)
        self.openocd_cmd = openocd_cmd

    def program(self, firmware_path: Path) -> list[str]:
        if not firmware_path.exists():
            return [f"Ошибка: файл прошивки '{firmware_path}' не найден."]
        if not self.config_path.exists():
            return [f"Ошибка: конфигурационный файл '{self.config_path}' не найден."]

        cmd = [
            self.openocd_cmd,
            '-f', str(self.config_path),
            '-c', 'init',
            '-c', f'svf {firmware_path}',
            '-c', 'shutdown'
        ]

        log_lines = [f"Запуск: {' '.join(cmd)}"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            if result.stdout:
                log_lines.append("STDOUT:\n" + result.stdout)
            if result.stderr:
                log_lines.append("STDERR:\n" + result.stderr)
            log_lines.append("Прошивка успешно загружена.")
        except subprocess.CalledProcessError as e:
            log_lines.append(f"Ошибка OpenOCD (код {e.returncode}):")
            if e.stdout:
                log_lines.append("STDOUT:\n" + e.stdout)
            if e.stderr:
                log_lines.append("STDERR:\n" + e.stderr)
            if "permission" in e.stderr.lower() or "insufficient permissions" in e.stderr.lower():
                log_lines.append("Возможно, недостаточно прав для USB-Blaster. Проверьте правила udev.")
        except subprocess.TimeoutExpired:
            log_lines.append("Ошибка: превышен таймаут 120 секунд.")
        return log_lines


class RealCamera:
    """
    Реальная камера. Захват видео через ffmpeg напрямую с V4L2,
    без перекодирования (MJPG → контейнер as-is).
    Минимизирует нагрузку на USB-шину.
    Fallback на OpenCV если ffmpeg недоступен.
    """

    def __init__(
        self,
        fps: int = 30,
        width: int = 640,
        height: int = 480,
        device: str = "/dev/video0",
    ) -> None:
        self.fps = fps
        self.width = width
        self.height = height
        self.device = device

    def capture(self, video_path: Path, duration_sec: float) -> list[str]:
        """Пробует ffmpeg, при неудаче — OpenCV fallback."""
        log = self._capture_ffmpeg(video_path, duration_sec)
        if video_path.exists() and video_path.stat().st_size > 0:
            return log

        # ffmpeg не сработал — пробуем OpenCV
        log.append("[RealCamera] ffmpeg-захват не удался, пробуем OpenCV fallback...")
        fallback_log = self._capture_opencv(video_path, duration_sec)
        return log + fallback_log

    # ------------------------------------------------------------------
    # Способ 1: ffmpeg (основной)
    # ------------------------------------------------------------------

    def _capture_ffmpeg(self, video_path: Path, duration_sec: float) -> list[str]:
        """
        Захват через ffmpeg -f v4l2.
        Ключевой момент: -c:v copy — ffmpeg читает MJPG-кадры с камеры
        и кладёт их в контейнер БЕЗ декодирования/кодирования.
        Нагрузка на CPU = 0, нагрузка на USB = минимум (только сырой поток).
        """
        log_lines: list[str] = []

        # Сначала пишем в .avi (MJPG нативно ложится в AVI)
        avi_path = video_path.with_suffix(".avi")

        cmd = [
            "ffmpeg", "-y",
            # Входной поток: V4L2 камера
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps),
            "-i", self.device,
            # Длительность
            "-t", f"{duration_sec:.1f}",
            # БЕЗ перекодирования — ключ к скорости
            "-c:v", "copy",
            str(avi_path),
        ]

        log_lines.append(f"[RealCamera] ffmpeg команда: {' '.join(cmd)}")
        start_time = time.monotonic()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(duration_sec) + 30,
            )
            elapsed = time.monotonic() - start_time

            if result.returncode != 0:
                log_lines.append(f"[RealCamera] ffmpeg код возврата: {result.returncode}")
                if result.stderr:
                    # Берём последние 20 строк stderr (там основная диагностика)
                    stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:])
                    log_lines.append(f"[RealCamera] ffmpeg stderr:\n{stderr_tail}")
                return log_lines

            # Парсим fps из stderr ffmpeg
            actual_fps = self._parse_ffmpeg_fps(result.stderr)
            if result.stderr:
                stderr_tail = "\n".join(result.stderr.strip().splitlines()[-5:])
                log_lines.append(f"[RealCamera] ffmpeg вывод:\n{stderr_tail}")

            log_lines.append(
                f"[RealCamera] ffmpeg захват завершён за {elapsed:.2f} сек"
                + (f", FPS ≈ {actual_fps:.1f}" if actual_fps else "")
            )

        except FileNotFoundError:
            log_lines.append("[RealCamera] ffmpeg не найден.")
            return log_lines
        except subprocess.TimeoutExpired:
            log_lines.append(f"[RealCamera] ffmpeg таймаут ({duration_sec + 30} сек).")
            return log_lines

        # Конвертируем .avi → .mp4 (если нужен mp4)
        if video_path.suffix.lower() == ".mp4" and avi_path.exists():
            converted = self._avi_to_mp4(avi_path, video_path, log_lines)
            if not converted:
                # Если конвертация не удалась — переименуем
                try:
                    avi_path.rename(video_path)
                except OSError:
                    pass
        elif avi_path.exists() and avi_path != video_path:
            try:
                avi_path.rename(video_path)
            except OSError:
                pass

        return log_lines

    @staticmethod
    def _parse_ffmpeg_fps(stderr: str) -> float | None:
        """Извлекает средний fps из вывода ffmpeg."""
        # ffmpeg пишет строки вида "frame=  450 fps= 29 ..."
        import re
        matches = re.findall(r"fps=\s*([\d.]+)", stderr)
        if matches:
            try:
                return float(matches[-1])
            except ValueError:
                pass
        return None

    @staticmethod
    def _avi_to_mp4(avi_path: Path, mp4_path: Path, log_lines: list[str]) -> bool:
        """Конвертирует MJPG .avi → H.264 .mp4."""
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(avi_path),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "fast",
                    "-crf", "23",
                    str(mp4_path),
                ],
                capture_output=True,
                timeout=120,
                check=True,
            )
            avi_path.unlink(missing_ok=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log_lines.append(f"[RealCamera] avi→mp4 конвертация не удалась: {exc}")
            return False

    # ------------------------------------------------------------------
    # Способ 2: OpenCV fallback
    # ------------------------------------------------------------------

    def _capture_opencv(self, video_path: Path, duration_sec: float) -> list[str]:
        if cv2 is None:
            video_path.write_bytes(b"NO CV2 INSTALLED\n")
            return ["[RealCamera] OpenCV не установлен, создан файл-заглушка."]

        cap = self._open_capture()
        if cap is None:
            return ["[RealCamera] OpenCV: не удалось открыть камеру."]

        try:
            return self._do_capture_opencv(cap, video_path, duration_sec)
        finally:
            cap.release()

    @staticmethod
    def _open_capture() -> "cv2.VideoCapture | None":
        backends: list[int] = []
        if hasattr(cv2, 'CAP_DSHOW'):
            backends.append(cv2.CAP_DSHOW)
        if hasattr(cv2, 'CAP_V4L2'):
            backends.append(cv2.CAP_V4L2)
        backends.append(cv2.CAP_ANY)

        for backend in backends:
            cap = cv2.VideoCapture(0, backend)
            if cap.isOpened():
                return cap
        return None

    def _do_capture_opencv(
        self,
        cap: "cv2.VideoCapture",
        video_path: Path,
        duration_sec: float,
    ) -> list[str]:
        log_lines: list[str] = []

        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        # Прогрев
        for _ in range(15):
            cap.read()

        frames: list[np.ndarray] = []
        timestamps: list[float] = []
        start_time = time.monotonic()

        while True:
            ret, frame = cap.read()
            now = time.monotonic()
            if not ret or (now - start_time) >= duration_sec:
                break
            frames.append(frame)
            timestamps.append(now)

        total_time = time.monotonic() - start_time

        if len(frames) < 2:
            return [f"[RealCamera] OpenCV: получено {len(frames)} кадров за {total_time:.2f} сек."]

        real_fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        h_act, w_act = frames[0].shape[:2]

        avi_path = video_path.with_suffix(".avi")
        out_fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(str(avi_path), out_fourcc, real_fps, (w_act, h_act))
        if not out.isOpened():
            out_fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            out = cv2.VideoWriter(str(avi_path), out_fourcc, real_fps, (w_act, h_act))
        if not out.isOpened():
            return ["[RealCamera] OpenCV: не удалось создать VideoWriter."]

        for frame in frames:
            out.write(frame)
        out.release()

        if video_path.suffix.lower() == ".mp4":
            if not self._avi_to_mp4(avi_path, video_path, log_lines):
                try:
                    avi_path.rename(video_path)
                except OSError:
                    pass

        log_lines.extend([
            f"[RealCamera] OpenCV fallback: {len(frames)} кадров, {real_fps:.2f} fps, {total_time:.2f} сек.",
            f"  Путь: {video_path}",
        ])
        return log_lines


class CameraStub:
    """Заглушка камеры (оставлена для тестов)"""
    def __init__(self) -> None:
        self._video_path: Path | None = None

    def capture(self, video_path: Path, duration_sec: float) -> list[str]:
        self._video_path = video_path
        video_path.write_bytes(b"STUB VIDEO PLACEHOLDER\n")
        return [
            "[STUB] Camera capture started.",
            f"[STUB] Target video path: {video_path}",
            f"[STUB] Simulated capture duration: {duration_sec} sec.",
            "[STUB] Camera capture stopped.",
        ]

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
    def __init__(self, *, programmer: RealProgrammer | None = None, camera: RealCamera | None = None):
        self.programmer = programmer or RealProgrammer()
        self.camera = camera or RealCamera()

    def run(self, *, firmware_path: Path, workspace: Path, timeout_seconds: int, record_duration_sec: float = 15.0) -> ExecutionResult:
        workspace.mkdir(parents=True, exist_ok=True)
        video_path = workspace / "result.mp4"
        log_lines: list[str] = []
        started_at = time.monotonic()

        # 1. Прошивка
        log_lines.append("=== Начало прошивки FPGA ===")
        prog_log = self.programmer.program(firmware_path)
        log_lines.extend(prog_log)
        programming_ok = any("успешно" in line for line in prog_log) and not any("Ошибка" in line for line in prog_log)

        if not programming_ok:
            log_lines.append("Прошивка не удалась, запись видео не будет выполнена.")
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log_lines),
                video_path=video_path,
                error_message="Programming failed",
            )

        # 2. Запись видео
        elapsed = time.monotonic() - started_at
        remaining_time = timeout_seconds - elapsed
        if remaining_time <= 0:
            log_lines.append("Время ожидания истекло до начала записи видео.")
            return ExecutionResult(
                status="error",
                execution_log="\n".join(log_lines),
                video_path=video_path,
                error_message="Timeout before video recording",
            )

        effective_record_duration = min(record_duration_sec, remaining_time)
        log_lines.append(f"=== Начало записи видео ({effective_record_duration} сек.) ===")
        try:
            record_log = self.camera.capture(video_path, effective_record_duration)
            log_lines.extend(record_log)

            actual_video: Path | None = None
            for suffix in (".mp4", ".avi"):
                candidate = video_path.with_suffix(suffix)
                if candidate.exists() and candidate.stat().st_size > 0:
                    actual_video = candidate
                    break

            status = "completed" if actual_video else "error"
            error_message = "" if actual_video else "Видеофайл не создан"

        except Exception as exc:
            status = "error"
            error_message = str(exc)
            log_lines.append(f"Ошибка при записи видео: {exc}")
            actual_video = None

        log_lines.append("=== Выполнение завершено ===")
        return ExecutionResult(
            status=status,
            execution_log="\n".join(log_lines),
            video_path=actual_video,
            error_message=error_message,
        )
