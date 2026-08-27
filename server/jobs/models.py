from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .constants import HEARTBEAT_TTL_SECONDS, PIN_COUNT


def generate_agent_token() -> str:
    return secrets.token_hex(24)


def generate_session_token() -> str:
    return secrets.token_hex(24)


def firmware_upload_to(instance: "Job", filename: str) -> str:
    suffix = Path(filename).suffix
    return f"firmware/{instance.id}{suffix}"


def instruction_upload_to(instance: "Job", filename: str) -> str:
    return f"instructions/{instance.id}.txt"


def result_video_upload_to(instance: "Job", filename: str) -> str:
    suffix = Path(filename).suffix or ".mp4"
    return f"results/{instance.id}{suffix}"


def session_flash_upload_to(instance: "StandSession", filename: str) -> str:
    suffix = Path(filename).suffix or ".svf"
    return f"session_flash/{instance.id}{suffix}"


def default_pin_states() -> list[bool]:
    return [False] * PIN_COUNT


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Agent(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    token = models.CharField(max_length=64, unique=True, default=generate_agent_token, editable=False)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def touch(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at", "updated_at"])

    @property
    def is_online(self) -> bool:
        if not self.is_active or self.last_seen_at is None:
            return False
        return timezone.now() - self.last_seen_at <= timedelta(seconds=HEARTBEAT_TTL_SECONDS)

    def computed_status(self) -> str:
        if not self.is_online:
            return "offline"
        has_session = self.sessions.filter(
            released_at__isnull=True,
            ends_at__gt=timezone.now(),
        ).exists()
        has_running_job = self.claimed_jobs.filter(status=Job.Status.RUNNING).exists()
        if has_session or has_running_job:
            return "busy"
        return "idle"


class Job(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "waiting", "ожидает"
        RUNNING = "running", "выполняется"
        COMPLETED = "completed", "завершено"
        ERROR = "error", "ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="jobs")
    target_agent = models.ForeignKey(
        Agent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="queued_jobs",
    )
    firmware = models.FileField(upload_to=firmware_upload_to)
    original_filename = models.CharField(max_length=255)
    instruction = models.FileField(upload_to=instruction_upload_to, null=True, blank=True)
    instruction_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING)
    claimed_by = models.ForeignKey(
        Agent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    execution_log = models.TextField(blank=True)
    result_video = models.FileField(upload_to=result_video_upload_to, null=True, blank=True)
    error_message = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.original_filename} [{self.get_status_display()}]"

    @property
    def queue_position(self) -> int | None:
        if self.status != self.Status.WAITING:
            return None
        waiting = Job.objects.filter(status=self.Status.WAITING)
        if self.target_agent_id:
            waiting = waiting.filter(target_agent_id=self.target_agent_id)
        return waiting.filter(created_at__lt=self.created_at).count() + 1

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline_at and self.deadline_at < timezone.now())


class StandSession(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="sessions")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stand_sessions")
    token = models.CharField(max_length=64, unique=True, default=generate_session_token, editable=False)
    started_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    pending_flash = models.FileField(upload_to=session_flash_upload_to, null=True, blank=True)
    pending_flash_name = models.CharField(max_length=255, blank=True)
    pending_commands = models.JSONField(default=list, blank=True)
    pin_states = models.JSONField(default=default_pin_states)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"session {self.agent} / {self.owner}"

    @property
    def is_active(self) -> bool:
        if self.released_at is not None:
            return False
        return self.ends_at > timezone.now()
