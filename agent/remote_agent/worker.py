from __future__ import annotations

import logging
import time
from pathlib import Path

from .api import ServerClient, ServerError
from .config import AgentConfig
from .hardware import GpioDriver, HardwareExecutor, StubGpio
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
        token: str = "",
    ) -> None:
        self.config = config
        self.client = client
        self.executor = executor
        self.gpio = gpio or StubGpio()
        self.token = token or config.token
        self._streamer: CameraStreamer | None = None

    def run(self) -> None:
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                try:
                    heartbeat = self.client.heartbeat()
                except ServerError as exc:
                    logger.warning("[AGENT] Сервер недоступен: %s", exc)
                    self._stop_stream()
                    time.sleep(self.config.poll_interval)
                    continue

                try:
                    session = self.client.get_session()
                except ServerError as exc:
                    logger.warning("[AGENT] Не удалось опросить сессию: %s", exc)
                    time.sleep(self.config.poll_interval)
                    continue

                if session:
                    self._handle_session(session)
                    time.sleep(0.4)
                    continue

                self._stop_stream()
                if heartbeat.get("has_session"):
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
        except KeyboardInterrupt:
            logger.info("[AGENT] Остановка.")
            self._stop_stream()

    def _handle_session(self, session: dict) -> None:
        self._ensure_stream()
        workspace = self.config.workspace / "session"
        workspace.mkdir(parents=True, exist_ok=True)
        for command in session.get("commands") or []:
            kind = command.get("kind")
            if kind == "pin":
                try:
                    self.gpio.set_pin(int(command["pin"]), command.get("state") == "high")
                except Exception as exc:
                    logger.warning("GPIO command failed: %s", exc)
            elif kind == "flash":
                flash_url = session.get("flash_url")
                if not flash_url:
                    continue
                filename = session.get("flash_name") or "session.svf"
                path = workspace / filename
                try:
                    self.client.download_file(flash_url, path)
                    log = self.executor.programmer.program(path)
                    logger.info("Sync flash: %s", " | ".join(log[-3:]))
                except Exception as exc:
                    logger.warning("Sync flash failed: %s", exc)

    def _ensure_stream(self) -> None:
        if self._streamer is not None:
            return
        url = f"{self.client.ws_base()}/ws/camera/exporter/?token={self.token}"
        self._streamer = CameraStreamer(url=url, gpio=self.gpio)
        self._streamer.start()

    def _stop_stream(self) -> None:
        if self._streamer is not None:
            self._streamer.stop()
            self._streamer = None

    def _process_job_safe(self, job: RemoteJob) -> None:
        try:
            self._process_job(job)
        except ServerError as exc:
            logger.error("[AGENT] Ошибка связи во время задачи %s: %s", job.id, exc)
        except Exception as exc:
            logger.error("[AGENT] Неожиданная ошибка задачи %s: %s", job.id, exc)
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

        logger.info("[AGENT] Запускаю выполнение задачи %s...", job.id)
        result = self.executor.run(
            firmware_path=firmware_path,
            instruction_text=instruction_text,
            workspace=job_workspace,
            timeout_seconds=self.config.timeout_seconds,
            record_duration_sec=float(self.config.record_duration_sec),
        )
        logger.info("[AGENT] Отправляю результат задачи %s (статус: %s)...", job.id, result.status)
        self.client.submit_result(job=job, result=result)

    def _try_submit_error(self, job: RemoteJob, error_message: str) -> None:
        try:
            result = ExecutionResult(
                status="error",
                execution_log="",
                error_message=f"Агент упал с ошибкой: {error_message}",
            )
            self.client.submit_result(job=job, result=result)
        except Exception:
            pass
