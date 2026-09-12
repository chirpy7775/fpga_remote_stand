from __future__ import annotations

import logging
from pathlib import Path

import requests

from .models import ExecutionResult, RemoteJob

logger = logging.getLogger(__name__)


class ServerError(Exception):
    """Ошибка при общении с сервером."""


class ServerClient:
    def __init__(self, *, server_url: str, token: str = "", gpio_pins: tuple[int, ...] | None = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.gpio_pins = gpio_pins
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})

    def ws_base(self) -> str:
        if self.server_url.startswith("https://"):
            return "wss://" + self.server_url.removeprefix("https://")
        return "ws://" + self.server_url.removeprefix("http://")

    def heartbeat(self) -> dict:
        try:
            response = self.session.post(
                f"{self.server_url}/agent/api/heartbeat/",
                json={"gpio_pins": list(self.gpio_pins)} if self.gpio_pins is not None else {},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"heartbeat failed: {exc}") from exc

    def get_session(self) -> dict | None:
        try:
            response = self.session.get(f"{self.server_url}/agent/api/session/", timeout=10)
            response.raise_for_status()
            return response.json().get("session")
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"session poll failed: {exc}") from exc

    def download_file(self, url: str, destination: Path) -> Path:
        try:
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_handle.write(chunk)
            return destination
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"download failed: {exc}") from exc

    def claim_job(self) -> RemoteJob | None:
        try:
            response = self.session.post(f"{self.server_url}/agent/api/jobs/claim/", timeout=10)
            response.raise_for_status()
            payload = response.json().get("job")
            if payload is None:
                return None
            return RemoteJob.from_payload(payload)
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"claim failed: {exc}") from exc

    def download_firmware(self, *, job: RemoteJob, destination: Path) -> Path:
        return self.download_file(job.download_url, destination)

    def download_instruction(self, *, job: RemoteJob, destination: Path) -> Path | None:
        if not job.instruction_url:
            return None
        return self.download_file(job.instruction_url, destination)

    def submit_result(self, *, job: RemoteJob, result: ExecutionResult) -> dict:
        data = {
            "status": result.status,
            "execution_log": result.execution_log,
            "error_message": result.error_message,
        }
        files = {}
        if result.video_path is not None and result.video_path.exists():
            content_type = "video/mp4" if result.video_path.suffix.lower() == ".mp4" else "image/png"
            files["result_video"] = (
                result.video_path.name,
                result.video_path.open("rb"),
                content_type,
            )
        try:
            response = self.session.post(job.result_url, data=data, files=files, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            raise ServerError(f"submit failed: {exc}") from exc
        finally:
            file_obj = files.get("result_video")
            if file_obj:
                file_obj[1].close()
