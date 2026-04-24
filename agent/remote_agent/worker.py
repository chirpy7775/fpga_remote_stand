from __future__ import annotations

import logging
import time
from pathlib import Path

from .api import ServerClient, ServerError
from .config import AgentConfig
from .hardware import HardwareExecutor
from .models import RemoteJob

logger = logging.getLogger(__name__)


class AgentWorker:
    def __init__(self, *, config: AgentConfig, client: ServerClient, executor: HardwareExecutor) -> None:
        self.config = config
        self.client = client
        self.executor = executor

    def run(self) -> None:
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                try:
                    job = self.client.claim_job()
                except ServerError as exc:
                    logger.warning("[AGENT] Не удалось получить задачу: %s", exc)
                    logger.warning("[AGENT] Сервер недоступен: %s", exc)
                    logger.info("[AGENT] Повтор через %s сек...", self.config.poll_interval)
                    time.sleep(self.config.poll_interval)
                    continue

                if job is None:
                    time.sleep(self.config.poll_interval)
                    continue

                self._process_job_safe(job)
        except KeyboardInterrupt:
            logger.info("[AGENT] Остановка.")

    def _process_job_safe(self, job: RemoteJob) -> None:
        """Выполняет задачу. При любой ошибке логирует и не падает."""
        try:
            self._process_job(job)
        except ServerError as exc:
            # Сервер упал во время выполнения — задача останется
            # в статусе running до истечения таймаута на сервере
            logger.error("[AGENT] Ошибка связи во время выполнения задачи %s: %s", job.id, exc)
        except Exception as exc:
            logger.error("[AGENT] Неожиданная ошибка при выполнении задачи %s: %s", job.id, exc)
            self._try_submit_error(job, str(exc))

    def _process_job(self, job: RemoteJob) -> None:
        job_workspace = self.config.workspace / job.id
        firmware_path = job_workspace / job.original_filename

        logger.info("[AGENT] Скачиваю прошивку для задачи %s...", job.id)
        self.client.download_firmware(job=job, destination=firmware_path)

        logger.info("[AGENT] Запускаю выполнение задачи %s...", job.id)
        result = self.executor.run(
            firmware_path=firmware_path,
            workspace=job_workspace,
            timeout_seconds=self.config.timeout_seconds,
            record_duration_sec=float(self.config.record_duration_sec),
        )

        logger.info("[AGENT] Отправляю результат задачи %s (статус: %s)...", job.id, result.status)
        self.client.submit_result(job=job, result=result)
        logger.info("[AGENT] Задача %s завершена.", job.id)

    def _try_submit_error(self, job: RemoteJob, error_message: str) -> None:
        """Пробует сообщить серверу об ошибке. Если не получается — молча пропускает."""
        try:
            from .models import ExecutionResult
            result = ExecutionResult(
                status="error",
                execution_log="",
                error_message=f"Агент упал с ошибкой: {error_message}",
            )
            self.client.submit_result(job=job, result=result)
        except Exception:
            pass