from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time
from pathlib import Path

from .hardware import DEFAULT_FPS, PIN_COUNT, ProgramResult

try:
    import lgpio
except ImportError:  # не Raspberry Pi — RealGpio просто нельзя использовать
    lgpio = None

logger = logging.getLogger(__name__)

# Логический пин стенда 1..8 → BCM-номер на Raspberry Pi.
# Должен совпадать с PIN_MAP в server/jobs/constants.py.
PIN_BCM: tuple[int, ...] = (21, 20, 16, 12, 1, 7, 8, 25)

# Камера отдаёт MJPG 640x480@30 — снимаем как есть, без перекодирования.
CAPTURE_WIDTH = 640
CAPTURE_HEIGHT = 480
CAPTURE_FPS = 30

_OPENOCD_SUCCESS = "programmed successfully"

# Сколько символов ffmpeg-шума пускаем в лог задачи.
STDERR_LOG_LIMIT = 4000


class RealProgrammer:
    """Заливает .svf на MAX 10 через OpenOCD и USB-Blaster."""

    def __init__(self, config_path: Path | None = None, openocd_cmd: str = "openocd") -> None:
        if config_path is None:
            config_path = Path(__file__).parent.parent / "utils" / "board" / "max10.cfg"
        self.config_path = Path(config_path)
        self.openocd_cmd = openocd_cmd

    def program(self, firmware_path: Path) -> ProgramResult:
        if not firmware_path.exists():
            return ProgramResult(False, [f"Файл прошивки не найден: {firmware_path}"])
        if not self.config_path.exists():
            return ProgramResult(False, [f"Конфиг OpenOCD не найден: {self.config_path}"])

        command = [
            self.openocd_cmd,
            "-f", str(self.config_path),
            "-c", "init",
            "-c", f"svf {firmware_path}",
            "-c", "shutdown",
        ]
        log = [f"Запуск: {' '.join(command)}"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            return ProgramResult(False, log + ["OpenOCD не установлен."])
        except subprocess.TimeoutExpired:
            return ProgramResult(False, log + ["OpenOCD не ответил за 180 с."])

        output = f"{result.stdout}\n{result.stderr}".strip()
        log.append(output)
        # OpenOCD печатает предупреждения даже при успехе, поэтому ориентируемся
        # только на итоговую строку про успешную заливку.
        ok = result.returncode == 0 and _OPENOCD_SUCCESS in output
        if ok:
            log.append("Прошивка загружена.")
        else:
            log.append(f"Прошивка не удалась (код {result.returncode}).")
            if "permission" in output.lower():
                log.append("Похоже на права доступа к USB-Blaster: проверьте правила udev.")
        return ProgramResult(ok, log)


class RealGpio:
    """
    Восемь линий стенда через lgpio.

    В покое линии отпущены во входы: так малина не спорит за пин с битстримом,
    который держит тот же вывод выходом. На время задачи или сессии линии
    забираются целиком через engage() — иначе неуправляемый пин подтягивался бы
    платой вверх и выглядел бы как high.
    """

    def __init__(self, chip: int = 0) -> None:
        self._chip = chip
        self._handle: int | None = None
        self._driven: set[int] = set()
        self._states = [False] * PIN_COUNT

    def engage(self) -> None:
        handle = self._open()
        for bcm in PIN_BCM:
            if bcm not in self._driven:
                lgpio.gpio_claim_output(handle, bcm, 0)
                self._driven.add(bcm)
            else:
                lgpio.gpio_write(handle, bcm, 0)
        self._states = [False] * PIN_COUNT
        logger.info("GPIO захвачен: восемь линий выставлены в low")

    def set_pin(self, pin: int, high: bool) -> str:
        if pin < 1 or pin > PIN_COUNT:
            raise ValueError(f"Пин {pin} вне диапазона 1..{PIN_COUNT}")
        bcm = PIN_BCM[pin - 1]
        handle = self._open()
        if bcm not in self._driven:
            lgpio.gpio_claim_output(handle, bcm, 0)
            self._driven.add(bcm)
        lgpio.gpio_write(handle, bcm, 1 if high else 0)
        self._states[pin - 1] = high
        level = "high" if high else "low"
        logger.info("GPIO pin=%s bcm=%s %s", pin, bcm, level)
        return f"[GPIO] pin {pin} (BCM {bcm}) {level}"

    def snapshot(self) -> list[bool]:
        return list(self._states)

    def release(self) -> None:
        """
        Перевести все линии в высокий импеданс.

        Одного gpio_free мало: пад остаётся выходом и продолжает тянуть low, а
        это худший вид спора с платой, если чужой битстрим держит тот же вывод
        выходом в high. Поэтому сначала явно объявляем линию входом без
        подтяжек — только после этого она действительно отпущена.
        """
        if self._handle is None:
            self._states = [False] * PIN_COUNT
            return
        for bcm in sorted(self._driven):
            try:
                lgpio.gpio_claim_input(self._handle, bcm, lgpio.SET_PULL_NONE)
                lgpio.gpio_free(self._handle, bcm)
            except Exception:
                logger.warning("Не удалось освободить BCM %s", bcm, exc_info=True)
        self._driven.clear()
        self._states = [False] * PIN_COUNT
        try:
            lgpio.gpiochip_close(self._handle)
        except Exception:
            logger.warning("Не удалось закрыть gpiochip", exc_info=True)
        self._handle = None
        logger.info("GPIO освобождён (линии переведены во входы)")

    def _open(self) -> int:
        if self._handle is None:
            if lgpio is None:
                raise RuntimeError("Модуль lgpio недоступен: нужен Raspberry Pi (apt install python3-lgpio).")
            self._handle = lgpio.gpiochip_open(self._chip)
            logger.info("gpiochip%s открыт", self._chip)
        return self._handle


class RealCamera:
    """
    Единственный владелец /dev/video0.

    Запись и живой стрим не могут идти одновременно (устройство одно), поэтому
    старт записи закрывает стрим, а следующий запрос кадра поднимает его заново.
    """

    def __init__(
        self,
        device: str = "/dev/video0",
        fps: int = DEFAULT_FPS,
        workspace: Path | None = None,
    ) -> None:
        self.fps = fps  # тайминг сценария: write_frame N == N / fps секунд
        self.device = device
        self._workspace = workspace or Path("workspace")
        self._recorder: subprocess.Popen | None = None
        self._raw_path: Path | None = None
        self._live: _MjpegPipe | None = None
        self._live_retry_at = 0.0
        self._stderr_path: Path | None = None
        self._stderr_file = None
        # Стрим живёт в своём потоке, запись — в основном. Замок гарантирует,
        # что они не откроют /dev/video0 одновременно.
        self._lock = threading.Lock()

    # --- запись результата асинхронной задачи ---------------------------------

    def start_recording(self) -> list[str]:
        with self._lock:
            return self._start_recording()

    def _start_recording(self) -> list[str]:
        self._stop_live()
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._raw_path = self._workspace / "capture.mkv"
        self._raw_path.unlink(missing_ok=True)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
            "-framerate", str(CAPTURE_FPS),
            "-i", self.device,
            "-c:v", "copy",
            str(self._raw_path),
        ]
        # stderr пишем в файл, а не в pipe: во время записи его никто не читает,
        # и переполненный буфер остановил бы ffmpeg посреди сценария.
        self._stderr_path = self._workspace / "capture-ffmpeg.log"
        try:
            self._stderr_file = self._stderr_path.open("wb")
            self._recorder = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_file,
            )
        except FileNotFoundError:
            self._close_stderr_file()
            self._recorder = None
            return ["ffmpeg не установлен, видео не будет записано."]
        time.sleep(1.0)  # даём камере прогреться, иначе первые кадры чёрные
        return [f"Запись с {self.device} начата ({CAPTURE_WIDTH}x{CAPTURE_HEIGHT}@{CAPTURE_FPS})."]

    def hold_frames(self, frames: int, pins: list[bool]) -> None:
        time.sleep(frames / self.fps)

    def stop_recording(self, video_path: Path) -> list[str]:
        with self._lock:
            recorder, self._recorder = self._recorder, None
            raw_path, self._raw_path = self._raw_path, None
        if recorder is None or raw_path is None:
            return ["Запись не была запущена."]

        log: list[str] = []
        recorder.send_signal(signal.SIGINT)  # SIGINT заставляет ffmpeg закрыть контейнер
        try:
            recorder.wait(timeout=20)
        except subprocess.TimeoutExpired:
            recorder.kill()
            recorder.wait()
            log.append("ffmpeg не завершился штатно, убит принудительно.")
        log.extend(self._collect_stderr())

        if not raw_path.exists() or raw_path.stat().st_size == 0:
            return log + ["Сырой файл записи пуст."]
        log.append(f"Снято {raw_path.stat().st_size // 1024} КБ MJPEG.")
        log.extend(_transcode_to_h264(raw_path, video_path))
        raw_path.unlink(missing_ok=True)
        return log

    # --- живой стрим синхронной сессии ---------------------------------------

    def live_frame(self, pins: list[bool]) -> bytes | None:
        with self._lock:
            if self._recorder is not None:
                return None  # идёт запись, устройство занято
            pipe = self._ensure_live()
        return pipe.latest() if pipe else None

    def close(self) -> None:
        with self._lock:
            self._stop_live()
            if self._recorder is not None:
                self._recorder.kill()
                self._recorder.wait(timeout=5)
                self._recorder = None
                self._raw_path = None
            self._close_stderr_file()

    def _close_stderr_file(self) -> None:
        if self._stderr_file is not None:
            self._stderr_file.close()
            self._stderr_file = None

    def _collect_stderr(self) -> list[str]:
        self._close_stderr_file()
        path, self._stderr_path = self._stderr_path, None
        if path is None or not path.exists():
            return []
        text = path.read_text("utf-8", "replace").strip()
        path.unlink(missing_ok=True)
        if len(text) > STDERR_LOG_LIMIT:
            text = text[:STDERR_LOG_LIMIT] + " …(лог ffmpeg обрезан)"
        return [text] if text else []

    def _ensure_live(self) -> "_MjpegPipe | None":
        if self._live is not None and self._live.alive:
            return self._live
        self._stop_live()
        if time.monotonic() < self._live_retry_at:
            return None
        self._live_retry_at = time.monotonic() + 3.0
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
            "-framerate", str(CAPTURE_FPS),
            "-i", self.device,
            "-f", "image2pipe",
            "-c:v", "copy",
            "-",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except FileNotFoundError:
            logger.warning("ffmpeg не установлен, живой стрим недоступен")
            return None
        self._live = _MjpegPipe(process)
        logger.info("Живой MJPEG-стрим с %s запущен", self.device)
        return self._live

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None


class _MjpegPipe:
    """Читает поток JPEG из stdout ffmpeg и держит только последний целый кадр."""

    _SOI = b"\xff\xd8"
    _EOI = b"\xff\xd9"
    _MAX_BUFFER = 4 * 1024 * 1024

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._frame: bytes | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="mjpeg-reader", daemon=True)
        self._thread.start()

    @property
    def alive(self) -> bool:
        return not self._stop.is_set() and self._process.poll() is None

    def latest(self) -> bytes | None:
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._stop.set()
        if self._process.poll() is None:
            self._process.kill()
        self._thread.join(timeout=2)
        # Без wait() убитый ffmpeg остаётся зомби, и они копятся по сессиям.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg живого стрима не завершился")
        if self._process.stdout is not None:
            self._process.stdout.close()

    def _run(self) -> None:
        buffer = bytearray()
        stream = self._process.stdout
        assert stream is not None
        while not self._stop.is_set():
            chunk = stream.read(65536)
            if not chunk:
                break
            buffer.extend(chunk)
            end = buffer.rfind(self._EOI)
            if end == -1:
                if len(buffer) > self._MAX_BUFFER:
                    del buffer[:-self._MAX_BUFFER]
                continue
            start = buffer.rfind(self._SOI, 0, end)
            if start != -1:
                with self._lock:
                    self._frame = bytes(buffer[start : end + 2])
            del buffer[: end + 2]
        logger.info("Читатель MJPEG остановлен")


def _transcode_to_h264(raw_path: Path, video_path: Path) -> list[str]:
    """MJPEG → H.264 mp4. Сначала аппаратный кодек Pi, при неудаче — libx264."""
    attempts = [
        ("h264_v4l2m2m", ["-c:v", "h264_v4l2m2m", "-b:v", "2M"]),
        ("libx264", ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]),
    ]
    log: list[str] = []
    for name, encoder_args in attempts:
        video_path.unlink(missing_ok=True)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(raw_path),
            *encoder_args,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(video_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.append(f"Кодек {name}: {exc}")
            continue
        if result.returncode == 0 and video_path.exists() and video_path.stat().st_size > 0:
            log.append(f"Видео перекодировано в H.264 ({name}).")
            return log
        log.append(f"Кодек {name} не справился: {result.stderr.strip()[:300]}")

    video_path.unlink(missing_ok=True)
    return log + ["Не удалось перекодировать видео."]


__all__ = ["PIN_BCM", "RealCamera", "RealGpio", "RealProgrammer"]
