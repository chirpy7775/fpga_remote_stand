from __future__ import annotations

import secrets
import uuid
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone


def generate_agent_token() -> str:
    return secrets.token_hex(24)


def firmware_upload_to(instance: "Job", filename: str) -> str:
    suffix = Path(filename).suffix
    return f"firmware/{instance.id}{suffix}"


def result_video_upload_to(instance: "Job", filename: str) -> str:
    suffix = Path(filename).suffix or ".mp4"
    return f"results/{instance.id}{suffix}"


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


class Job(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "waiting", "ожидает"
        RUNNING = "running", "выполняется"
        COMPLETED = "completed", "завершено"
        ERROR = "error", "ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="jobs")
    firmware = models.FileField(upload_to=firmware_upload_to)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING)
    claimed_by = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    execution_log = models.TextField(blank=True)
    result_video = models.FileField(upload_to=result_video_upload_to, null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.original_filename} [{self.get_status_display()}]"

    def get_absolute_url(self) -> str:
        return reverse("jobs:job-detail", kwargs={"pk": self.pk})

    @property
    def queue_position(self) -> int | None:
        if self.status != self.Status.WAITING:
            return None
        return (
            Job.objects.filter(status=self.Status.WAITING, created_at__lt=self.created_at).count() + 1
        )

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline_at and self.deadline_at < timezone.now())
