from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from .models import Agent, Job, PUBLIC_OWNER_USERNAME

logger = logging.getLogger("jobs")


@dataclass(slots=True)
class JobCompletion:
    status: str
    execution_log: str = ""
    error_message: str = ""
    result_video: BinaryIO | None = None


class JobService:
    @staticmethod
    def get_public_owner() -> User:
        user, created = User.objects.get_or_create(username=PUBLIC_OWNER_USERNAME)
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            logger.info("Создан публичный пользователь username=%s", PUBLIC_OWNER_USERNAME)
        return user

    @staticmethod
    def create_job(*, owner, firmware: UploadedFile) -> Job:
        job = Job(
            owner=owner,
            firmware=firmware,
            original_filename=firmware.name,
        )
        job.save()
        logger.info(
            "Создана задача job_id=%s owner=%s filename=%s",
            job.id,
            owner.username,
            firmware.name,
        )
        return job

    @staticmethod
    def expire_timed_out_jobs() -> int:
        now = timezone.now()
        expired_jobs = Job.objects.filter(
            status=Job.Status.RUNNING,
            deadline_at__isnull=False,
            deadline_at__lt=now,
        ).only("id", "execution_log")
        expired_count = 0
        timeout_note = "\n[TIMEOUT] Задача завершена сервером по таймауту."

        for job in expired_jobs:
            execution_log = job.execution_log
            if timeout_note not in job.execution_log:
                execution_log = f"{job.execution_log}{timeout_note}".strip()
            updated = Job.objects.filter(id=job.id, status=Job.Status.RUNNING).update(
                status=Job.Status.ERROR,
                finished_at=now,
                error_message="Превышен лимит времени выполнения.",
                execution_log=execution_log,
            )
            if updated:
                expired_count += updated
                logger.warning("Задача завершена по таймауту job_id=%s", job.id)

        if expired_count:
            logger.info("Просрочено задач: %d", expired_count)
        return expired_count

    @staticmethod
    def claim_next_job(*, agent: Agent) -> Job | None:
        JobService.expire_timed_out_jobs()

        now = timezone.now()
        deadline = now + timedelta(seconds=settings.EXECUTION_TIMEOUT_SECONDS)
        guest_priority = Case(
            When(owner__username=PUBLIC_OWNER_USERNAME, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
        candidate_ids = list(
            Job.objects.filter(status=Job.Status.WAITING)
            .annotate(guest_priority=guest_priority)
            .order_by("guest_priority", "created_at")
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
                    job = Job.objects.get(id=job_id)
                    logger.info(
                        "Задача взята в работу job_id=%s agent=%s deadline=%s",
                        job.id,
                        agent.pk,
                        deadline.isoformat(),
                    )
                    return job

        agent.touch()
        logger.debug("Нет задач для агента agent=%s", agent.pk)
        return None

    @staticmethod
    def complete_job(*, job: Job, agent: Agent, completion: JobCompletion) -> Job:
        with transaction.atomic():
            current = (
                Job.objects.filter(id=job.id)
                .values("id", "status", "claimed_by_id", "deadline_at")
                .first()
            )
            if current is None:
                logger.error("Попытка завершить несуществующую задачу job_id=%s agent=%s", job.id, agent.pk)
                raise ValueError("Задача не найдена.")
            if current["claimed_by_id"] != agent.id:
                logger.warning(
                    "Агент пытается завершить чужую задачу job_id=%s agent=%s claimed_by=%s",
                    job.id,
                    agent.pk,
                    current["claimed_by_id"],
                )
                raise ValueError("Задача выдана другому агенту.")
            if current["status"] != Job.Status.RUNNING:
                logger.warning(
                    "Задача не в статусе RUNNING при завершении job_id=%s status=%s agent=%s",
                    job.id,
                    current["status"],
                    agent.pk,
                )
                raise ValueError("Задача не находится в состоянии выполнения.")

            now = timezone.now()
            status = (
                completion.status
                if completion.status in {Job.Status.COMPLETED, Job.Status.ERROR}
                else Job.Status.ERROR
            )

            deadline_at = current["deadline_at"]
            if deadline_at and now > deadline_at:
                status = Job.Status.ERROR
                completion.error_message = completion.error_message or "Превышен лимит времени выполнения."
                if "[TIMEOUT]" not in completion.execution_log:
                    completion.execution_log = (
                        f"{completion.execution_log}\n[TIMEOUT] Агент прислал результат после таймаута."
                    ).strip()
                logger.warning(
                    "Агент прислал результат после дедлайна job_id=%s agent=%s", job.id, agent.pk
                )

            updated = Job.objects.filter(
                id=job.id,
                claimed_by_id=agent.id,
                status=Job.Status.RUNNING,
            ).update(
                status=status,
                finished_at=now,
                execution_log=completion.execution_log,
                error_message=completion.error_message,
            )
            if not updated:
                logger.error(
                    "Гонка при завершении задачи job_id=%s agent=%s", job.id, agent.pk
                )
                raise ValueError("Задача уже обновлена другим процессом.")

            updated_job = Job.objects.get(id=job.id)
            if completion.result_video is not None:
                updated_job.result_video = completion.result_video
                updated_job.save(update_fields=["result_video", "updated_at"])

            logger.info(
                "Задача завершена job_id=%s status=%s agent=%s",
                job.id,
                status,
                agent.pk,
            )

        agent.touch()
        return updated_job