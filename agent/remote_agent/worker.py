from __future__ import annotations

import time
from pathlib import Path

from .api import ServerClient
from .config import AgentConfig
from .hardware import HardwareExecutor
from .models import RemoteJob


class AgentWorker:
    def __init__(self, *, config: AgentConfig, client: ServerClient, executor: HardwareExecutor) -> None:
        self.config = config
        self.client = client
        self.executor = executor

    def run(self) -> None:
        self.config.workspace.mkdir(parents=True, exist_ok=True)

        while True:
            job = self.client.claim_job()
            if job is None:
                if self.config.run_once:
                    return
                time.sleep(self.config.poll_interval)
                continue

            self.process_job(job)
            if self.config.run_once:
                return

    def process_job(self, job: RemoteJob) -> None:
        job_workspace = self.config.workspace / job.id
        firmware_path = job_workspace / job.original_filename
        self.client.download_firmware(job=job, destination=firmware_path)
        result = self.executor.run(
            firmware_path=firmware_path,
            workspace=job_workspace,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.client.submit_result(job=job, result=result)
