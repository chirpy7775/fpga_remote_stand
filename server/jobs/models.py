from __future__ import annotations

import secrets
import uuid
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

PUBLIC_OWNER_USERNAME = "public-upload"


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
    MAX_RETRIES = 3

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
    claimed_by = models.ForeignKey(
        Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    execution_log = models.TextField(blank=True)
    result_video = models.FileField(upload_to=result_video_upload_to, null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    source_job = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retries",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.original_filename} [{self.get_status_display()}]"

    def get_absolute_url(self) -> str:
        return reverse("jobs:job-detail", kwargs={"pk": self.pk})

    @property
    def can_retry(self) -> bool:
        return (
            self.status in {self.Status.ERROR, self.Status.COMPLETED}
            and self.retry_count < self.MAX_RETRIES
        )

    @property
    def queue_position(self) -> int | None:
        if self.status != self.Status.WAITING:
            return None
        guest_owner_q = models.Q(owner__username=PUBLIC_OWNER_USERNAME)
        waiting_jobs = Job.objects.filter(status=self.Status.WAITING)
        is_guest_job = self.owner.username == PUBLIC_OWNER_USERNAME

        if is_guest_job:
            ahead_count = waiting_jobs.filter(
                ~guest_owner_q | (guest_owner_q & models.Q(created_at__lt=self.created_at))
            ).count()
        else:
            ahead_count = waiting_jobs.filter(~guest_owner_q, created_at__lt=self.created_at).count()

        return ahead_count + 1

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline_at and self.deadline_at < timezone.now())