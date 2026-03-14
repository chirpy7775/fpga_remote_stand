from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from .models import Agent, Job


@dataclass(slots=True)
class JobCompletion:
    status: str
    execution_log: str = ""
    error_message: str = ""
    result_video: BinaryIO | None = None


class JobService:
    @staticmethod
    def get_public_owner() -> User:
        user, created = User.objects.get_or_create(username="public-upload")
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    @staticmethod
    def create_job(*, owner, firmware: UploadedFile) -> Job:
        job = Job(
            owner=owner,
            firmware=firmware,
            original_filename=firmware.name,
        )
        job.save()
        return job

    @staticmethod
    def expire_timed_out_jobs() -> int:
        now = timezone.now()
        expired_jobs = Job.objects.filter(
            status=Job.Status.RUNNING,
            deadline_at__isnull=False,
            deadline_at__lt=now,
        )
        expired_count = 0
        timeout_note = "\n[TIMEOUT] Задача завершена сервером по таймауту."

        for job in expired_jobs:
            job.status = Job.Status.ERROR
            job.finished_at = now
            job.error_message = "Превышен лимит времени выполнения."
            if timeout_note not in job.execution_log:
                job.execution_log = f"{job.execution_log}{timeout_note}".strip()
            job.save(update_fields=["status", "finished_at", "error_message", "execution_log", "updated_at"])
            expired_count += 1
        return expired_count

    @staticmethod
    def claim_next_job(*, agent: Agent) -> Job | None:
        JobService.expire_timed_out_jobs()

        now = timezone.now()
        deadline = now + timedelta(seconds=settings.EXECUTION_TIMEOUT_SECONDS)
        candidate_ids = list(
            Job.objects.filter(status=Job.Status.WAITING)
            .order_by("created_at")
            .values_list("id", flat=True)[:10]
        )

        for job_id in candidate_ids:
            with transaction.atomic():
                updated = Job.objects.filter(id=job_id, status=Job.Status.WAITING).update(
                    status=Job.Status.RUNNING,
                    claimed_by=agent,
                    started_at=now,
                    deadline_at=deadline,
                    error_message="",
                )
                if updated:
                    agent.touch()
                    return Job.objects.get(id=job_id)

        agent.touch()
        return None

    @staticmethod
    def complete_job(*, job: Job, agent: Agent, completion: JobCompletion) -> Job:
        if job.claimed_by_id != agent.id:
            raise ValueError("Задача выдана другому агенту.")
        if job.status != Job.Status.RUNNING:
            raise ValueError("Задача не находится в состоянии выполнения.")

        now = timezone.now()
        status = completion.status if completion.status in {Job.Status.COMPLETED, Job.Status.ERROR} else Job.Status.ERROR

        if job.deadline_at and now > job.deadline_at:
            status = Job.Status.ERROR
            completion.error_message = completion.error_message or "Превышен лимит времени выполнения."
            if "[TIMEOUT]" not in completion.execution_log:
                completion.execution_log = (
                    f"{completion.execution_log}\n[TIMEOUT] Агент прислал результат после таймаута."
                ).strip()

        job.status = status
        job.finished_at = now
        job.execution_log = completion.execution_log
        job.error_message = completion.error_message
        if completion.result_video is not None:
            job.result_video = completion.result_video
        job.save()
        agent.touch()
        return job
