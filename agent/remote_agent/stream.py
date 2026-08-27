from __future__ import annotations

import logging
import threading
import time

from websocket import WebSocketConnectionClosedException, create_connection

from .frames import render_stub_frame
from .hardware import GpioDriver

logger = logging.getLogger(__name__)


class CameraStreamer:
    def __init__(self, *, url: str, gpio: GpioDriver, fps: int = 8) -> None:
        self.url = url
        self.gpio = gpio
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
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        tick = 0
        while not self._stop.is_set():
            ws = None
            try:
                ws = create_connection(self.url, timeout=10)
                logger.info("Камера-стрим подключён")
                while not self._stop.is_set():
                    frame = render_stub_frame(self.gpio.snapshot(), tick)
                    ws.send_binary(frame)
                    tick += 1
                    time.sleep(self.interval)
            except (OSError, WebSocketConnectionClosedException, Exception) as exc:
                logger.warning("Стрим камеры: %s", exc)
                time.sleep(1.5)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
