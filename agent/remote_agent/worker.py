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

        while True:
            try:
                job = self.client.claim_job()
            except ServerError as exc:
                logger.warning("[AGENT] Не удалось получить задачу: %s", exc)
                print(f"[AGENT] Сервер недоступен: {exc}")
                if self.config.run_once:
                    return
                print(f"[AGENT] Повтор через {self.config.poll_interval} сек...")
                time.sleep(self.config.poll_interval)
                continue

            if job is None:
                if self.config.run_once:
                    return
                time.sleep(self.config.poll_interval)
                continue

            self._process_job_safe(job)

            if self.config.run_once:
                return

    def _process_job_safe(self, job: RemoteJob) -> None:
        """Выполняет задачу. При любой ошибке логирует и не падает."""
        try:
            self._process_job(job)
        except ServerError as exc:
            # Сервер упал во время выполнения — задача останется
            # в статусе running до истечения таймаута на сервере
            logger.error("[AGENT] Ошибка связи во время выполнения задачи %s: %s", job.id, exc)
            print(f"[AGENT] Ошибка связи во время задачи {job.id}: {exc}")
        except Exception as exc:
            logger.error("[AGENT] Неожиданная ошибка при выполнении задачи %s: %s", job.id, exc)
            print(f"[AGENT] Неожиданная ошибка в задаче {job.id}: {exc}")
            # Пробуем отправить ошибку на сервер
            self._try_submit_error(job, str(exc))

    def _process_job(self, job: RemoteJob) -> None:
        job_workspace = self.config.workspace / job.id
        firmware_path = job_workspace / job.original_filename

        print(f"[AGENT] Скачиваю прошивку для задачи {job.id}...")
        self.client.download_firmware(job=job, destination=firmware_path)

        print(f"[AGENT] Запускаю выполнение задачи {job.id}...")
        result = self.executor.run(
            firmware_path=firmware_path,
            workspace=job_workspace,
            timeout_seconds=self.config.timeout_seconds,
        )

        print(f"[AGENT] Отправляю результат задачи {job.id} (статус: {result.status})...")
        self.client.submit_result(job=job, result=result)
        print(f"[AGENT] Задача {job.id} завершена.")

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
