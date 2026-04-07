from __future__ import annotations

import time
import logging
from pathlib import Path

import requests

from .models import ExecutionResult, RemoteJob

logger = logging.getLogger(__name__)


class ServerError(Exception):
    """Ошибка при общении с сервером."""


class ServerClient:
    def __init__(self, *, server_url: str, token: str = "") -> None:
        self.server_url = server_url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})

    def claim_job(self) -> RemoteJob | None:
        try:
            response = self.session.post(
                f"{self.server_url}/agent/api/jobs/claim/",
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json().get("job")
            if payload is None:
                return None
            return RemoteJob.from_payload(payload)
        except requests.exceptions.ConnectionError as exc:
            raise ServerError(f"Сервер недоступен: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise ServerError(f"Таймаут при запросе задачи: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise ServerError(f"HTTP-ошибка при запросе задачи: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"Сетевая ошибка при запросе задачи: {exc}") from exc

    def download_firmware(self, *, job: RemoteJob, destination: Path) -> Path:
        try:
            response = self.session.get(job.download_url, stream=True, timeout=30)
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_handle.write(chunk)
            return destination
        except requests.exceptions.ConnectionError as exc:
            raise ServerError(f"Сервер недоступен при скачивании прошивки: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise ServerError(f"Таймаут при скачивании прошивки: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise ServerError(f"HTTP-ошибка при скачивании прошивки: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"Сетевая ошибка при скачивании прошивки: {exc}") from exc

    def submit_result(self, *, job: RemoteJob, result: ExecutionResult) -> dict:
        data = {
            "status": result.status,
            "execution_log": result.execution_log,
            "error_message": result.error_message,
        }
        files = {}
        if result.video_path is not None and result.video_path.exists():
            files["result_video"] = (
                result.video_path.name,
                result.video_path.open("rb"),
                "video/mp4",
            )
        try:
            response = self.session.post(
                job.result_url,
                data=data,
                files=files,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as exc:
            raise ServerError(f"Сервер недоступен при отправке результата: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise ServerError(f"Таймаут при отправке результата: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise ServerError(f"HTTP-ошибка при отправке результата: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"Сетевая ошибка при отправке результата: {exc}") from exc
        finally:
            file_obj = files.get("result_video")
            if file_obj:
                file_obj[1].close()
