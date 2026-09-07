from __future__ import annotations

import logging
import shutil
import time

from .api import ServerClient, ServerError
from .config import AgentConfig
from .hardware import Camera, GpioDriver, HardwareExecutor, StubCamera, StubGpio
from .models import ExecutionResult, RemoteJob
from .stream import CameraStreamer

logger = logging.getLogger(__name__)


class AgentWorker:
    def __init__(
        self,
        *,
        config: AgentConfig,
        client: ServerClient,
        executor: HardwareExecutor,
        gpio: GpioDriver | None = None,
        camera: Camera | None = None,
        token: str = "",
    ) -> None:
        self.config = config
        self.client = client
        self.executor = executor
        self.gpio = gpio or StubGpio()
        self.camera = camera or StubCamera()
        self.token = token or config.token
        self._streamer: CameraStreamer | None = None
        self._in_session = False

    def run(self) -> None:
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        try:
            self._loop()
        except KeyboardInterrupt:
            logger.info("[AGENT] Остановка.")
        finally:
            self._end_session()
            self.gpio.release()
            self.camera.close()

    def _loop(self) -> None:
        while True:
            try:
                heartbeat = self.client.heartbeat()
                session = self.client.get_session()
            except ServerError as exc:
                logger.warning("[AGENT] Сервер недоступен: %s", exc)
                self._stop_stream()
                time.sleep(self.config.poll_interval)
                continue

            if session:
                self._handle_session(session)
                time.sleep(0.4)
                continue

            self._end_session()
            if heartbeat.get("has_session"):
                # Сессия принадлежит стенду, но ещё не отдана нам — задачу не берём.
                time.sleep(0.4)
                continue

            try:
                job = self.client.claim_job()
            except ServerError as exc:
                logger.warning("[AGENT] Не удалось получить задачу: %s", exc)
                time.sleep(self.config.poll_interval)
                continue

            if job is None:
                time.sleep(self.config.poll_interval)
                continue

            self._process_job_safe(job)

    # --- синхронная сессия ----------------------------------------------------

    def _handle_session(self, session: dict) -> None:
        if not self._in_session:
            self._in_session = True
            self.gpio.engage()
        self._ensure_stream()
        self._apply_pin_states(session.get("pin_states") or [])
        if any(command.get("kind") == "flash" for command in session.get("commands") or []):
            self._flash_in_session(session)

    def _apply_pin_states(self, wanted: list[bool]) -> None:
        """
        Сервер — единственный источник истины по пинам: приводим железо к его
        состоянию. Так пины не разъезжаются, если агент перезапустился.
        """
        current = self.gpio.snapshot()
        for index, state in enumerate(wanted[: len(current)]):
            if bool(state) == current[index]:
                continue
            try:
                self.gpio.set_pin(index + 1, bool(state))
            except Exception:
                logger.warning("Не удалось выставить пин %s", index + 1, exc_info=True)

    def _flash_in_session(self, session: dict) -> None:
        flash_url = session.get("flash_url")
        if not flash_url:
            return
        workspace = self.config.workspace / "session"
        path = workspace / (session.get("flash_name") or "session.svf")
        try:
            self.client.download_file(flash_url, path)
        except ServerError as exc:
            logger.warning("Не удалось скачать прошивку сессии: %s", exc)
            return
        result = self.executor.programmer.program(path)
        logger.info("Прошивка в сессии: ok=%s | %s", result.ok, " | ".join(result.log[-2:]))

    def _ensure_stream(self) -> None:
        if self._streamer is not None:
            return
        url = f"{self.client.ws_base()}/ws/camera/exporter/?token={self.token}"
        self._streamer = CameraStreamer(url=url, gpio=self.gpio, camera=self.camera)
        self._streamer.start()

    def _stop_stream(self) -> None:
        if self._streamer is not None:
            self._streamer.stop()
            self._streamer = None

    def _end_session(self) -> None:
        """Сессия закончилась: гасим стрим, отпускаем камеру и линии."""
        self._stop_stream()
        if self._in_session:
            self._in_session = False
            # Без close() ffmpeg живого стрима остался бы висеть на /dev/video0
            # до следующей задачи.
            self.camera.close()
            self.gpio.release()
            logger.info("[AGENT] Сессия закрыта, камера и линии освобождены.")

    # --- асинхронная задача ---------------------------------------------------

    def _process_job_safe(self, job: RemoteJob) -> None:
        try:
            self._process_job(job)
        except ServerError as exc:
            logger.error("[AGENT] Ошибка связи во время задачи %s: %s", job.id, exc)
        except Exception as exc:
            logger.exception("[AGENT] Неожиданная ошибка задачи %s", job.id)
            # Освобождаем плату и камеру, иначе повиснет ffmpeg на /dev/video0.
            self.gpio.release()
            self.camera.close()
            self._try_submit_error(job, str(exc))

    def _process_job(self, job: RemoteJob) -> None:
        job_workspace = self.config.workspace / job.id
        firmware_path = job_workspace / job.original_filename
        logger.info("[AGENT] Скачиваю прошивку для задачи %s...", job.id)
        self.client.download_firmware(job=job, destination=firmware_path)

        instruction_text = "write_frame 30\n"
        if job.instruction_url:
            instruction_path = job_workspace / (job.instruction_filename or "instruction.txt")
            self.client.download_instruction(job=job, destination=instruction_path)
            instruction_text = instruction_path.read_text(encoding="utf-8")

        logger.info("[AGENT] Выполняю задачу %s...", job.id)
        result = self.executor.run(
            firmware_path=firmware_path,
            instruction_text=instruction_text,
            workspace=job_workspace,
            timeout_seconds=self.config.timeout_seconds,
            record_duration_sec=float(self.config.record_duration_sec),
        )
        logger.info("[AGENT] Отправляю результат %s (статус %s)...", job.id, result.status)
        self.client.submit_result(job=job, result=result)
        # Прошивка и видео уже на сервере — на карточке Pi их держать незачем.
        shutil.rmtree(job_workspace, ignore_errors=True)

    def _try_submit_error(self, job: RemoteJob, error_message: str) -> None:
        try:
            self.client.submit_result(
                job=job,
                result=ExecutionResult(
                    status="error",
                    execution_log="",
                    error_message=f"Агент упал с ошибкой: {error_message}",
                ),
            )
        except ServerError:
            logger.warning("Не удалось отправить ошибку задачи %s", job.id)
