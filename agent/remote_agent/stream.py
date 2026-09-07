from __future__ import annotations

import logging
import threading
import time

from websocket import create_connection

from .hardware import Camera, GpioDriver

logger = logging.getLogger(__name__)


class CameraStreamer:
    """Гонит кадры камеры в WebSocket сервера, пока идёт синхронная сессия."""

    def __init__(self, *, url: str, gpio: GpioDriver, camera: Camera, fps: int = 8) -> None:
        self.url = url
        self.gpio = gpio
        self.camera = camera
        self.interval = 1.0 / max(fps, 1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            connection = None
            try:
                connection = create_connection(self.url, timeout=10)
                logger.info("Камера-стрим подключён")
                while not self._stop.is_set():
                    frame = self.camera.live_frame(self.gpio.snapshot())
                    if frame:
                        connection.send_binary(frame)
                    time.sleep(self.interval)
            except Exception as exc:
                logger.warning("Стрим камеры: %s", exc)
                self._stop.wait(1.5)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        logger.debug("Не удалось закрыть стрим", exc_info=True)
