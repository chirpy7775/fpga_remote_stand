from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from .constants import PIN_COUNT, SESSION_DURATION_SECONDS
from .lite_lang import InstructionError, parse_instruction
from .models import Agent, Job, StandSession, default_pin_states
from .realtime import broadcast_job, broadcast_session

logger = logging.getLogger("jobs")


@dataclass(slots=True)
class JobCompletion:
    status: str
    execution_log: str = ""
    error_message: str = ""
    result_video: BinaryIO | None = None


def _require_svf(filename: str) -> None:
    if Path(filename).suffix.lower() != ".svf":
        raise ValueError("Разрешены только .svf файлы в качестве прошивки.")


def _require_txt(filename: str) -> None:
    if Path(filename).suffix.lower() != ".txt":
        raise ValueError("Разрешены только .txt файлы в качестве инструкции.")


class JobService:
    @staticmethod
    def create_job(
        *,
        owner,
        firmware: UploadedFile,
        instruction: UploadedFile,
        target_agent: Agent,
    ) -> Job:
        _require_svf(firmware.name)
        _require_txt(instruction.name)
        text = instruction.read()
        if isinstance(text, bytes):
            try:
                decoded = text.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Файл инструкции должен быть UTF-8.") from exc
        else:
            decoded = str(text)
        instruction.seek(0)
        parse_instruction(decoded)

        job = Job(
            owner=owner,
            firmware=firmware,
            original_filename=firmware.name,
            instruction=instruction,
            instruction_filename=instruction.name,
            target_agent=target_agent,
        )
        job.save()
        logger.info(
            "Создана задача job_id=%s owner=%s agent=%s filename=%s",
            job.id,
            owner.username,
            target_agent.name,
            firmware.name,
        )
        broadcast_job(job)
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
                broadcast_job(Job.objects.get(id=job.id))

        if expired_count:
            logger.info("Просрочено задач: %d", expired_count)
        return expired_count

    @staticmethod
    def claim_next_job(*, agent: Agent) -> Job | None:
        JobService.expire_timed_out_jobs()
        SessionService.expire_sessions()

        if SessionService.agent_has_active_session(agent):
            agent.touch()
            return None

        now = timezone.now()
        deadline = now + timedelta(seconds=settings.EXECUTION_TIMEOUT_SECONDS)
        candidate_ids = list(
            Job.objects.filter(status=Job.Status.WAITING, target_agent=agent)
            .order_by("created_at")
            .values_list("id", flat=True)[:10]
        )

        for job_id in candidate_ids:
            with transaction.atomic():
                updated = Job.objects.filter(
                    id=job_id,
                    status=Job.Status.WAITING,
                    target_agent=agent,
                ).update(
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
                    broadcast_job(job)
                    return job

        agent.touch()
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
                raise ValueError("Задача не найдена.")
            if current["claimed_by_id"] != agent.id:
                raise ValueError("Задача выдана другому агенту.")
            if current["status"] != Job.Status.RUNNING:
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

            updated = Job.objects.filter(
                id=job.id,
                claimed_by_id=agent.id,
                status=Job.Status.RUNNING,
            ).update(
                status=status,
                finished_at=now,
                execution_log=completion.execution_log,
                error_message=completion.error_message[:512],
            )
            if not updated:
                raise ValueError("Задача уже обновлена другим процессом.")

            updated_job = Job.objects.get(id=job.id)
            if completion.result_video is not None:
                updated_job.result_video = completion.result_video
                updated_job.save(update_fields=["result_video", "updated_at"])

        agent.touch()
        broadcast_job(updated_job)
        return updated_job


class SessionService:
    @staticmethod
    def expire_sessions() -> int:
        now = timezone.now()
        expired = StandSession.objects.filter(released_at__isnull=True, ends_at__lte=now)
        count = 0
        for session in expired:
            session.released_at = now
            session.save(update_fields=["released_at", "updated_at"])
            broadcast_session(session)
            count += 1
        return count

    @staticmethod
    def agent_has_active_session(agent: Agent) -> bool:
        SessionService.expire_sessions()
        return StandSession.objects.filter(
            agent=agent,
            released_at__isnull=True,
            ends_at__gt=timezone.now(),
        ).exists()

    @staticmethod
    def active_for_agent(agent: Agent) -> StandSession | None:
        SessionService.expire_sessions()
        return (
            StandSession.objects.filter(
                agent=agent,
                released_at__isnull=True,
                ends_at__gt=timezone.now(),
            )
            .select_related("agent", "owner")
            .first()
        )

    @staticmethod
    def active_for_user(user: User) -> StandSession | None:
        SessionService.expire_sessions()
        return (
            StandSession.objects.filter(
                owner=user,
                released_at__isnull=True,
                ends_at__gt=timezone.now(),
            )
            .select_related("agent", "owner")
            .first()
        )

    @staticmethod
    def take(*, user: User, agent: Agent, duration_seconds: int | None = None) -> StandSession:
        SessionService.expire_sessions()
        JobService.expire_timed_out_jobs()

        if not agent.is_online:
            raise ValueError("Стенд офлайн. Дождитесь агента.")
        if SessionService.agent_has_active_session(agent):
            raise ValueError("Стенд уже занят.")
        if agent.claimed_jobs.filter(status=Job.Status.RUNNING).exists():
            raise ValueError("Стенд выполняет асинхронную задачу.")
        existing = SessionService.active_for_user(user)
        if existing is not None:
            raise ValueError("У вас уже есть активная сессия.")

        seconds = duration_seconds or SESSION_DURATION_SECONDS
        seconds = max(60, min(seconds, 60 * 60))
        now = timezone.now()
        session = StandSession.objects.create(
            agent=agent,
            owner=user,
            started_at=now,
            ends_at=now + timedelta(seconds=seconds),
            pin_states=default_pin_states(),
            pending_commands=[],
        )
        logger.info("Сессия открыта session=%s agent=%s user=%s", session.id, agent.name, user.username)
        broadcast_session(session)
        return session

    @staticmethod
    def release(session: StandSession) -> StandSession:
        if session.released_at is None:
            session.released_at = timezone.now()
            session.save(update_fields=["released_at", "updated_at"])
            broadcast_session(session)
        return session

    @staticmethod
    def enqueue_pin(*, session: StandSession, pin: int, state: str) -> StandSession:
        if not session.is_active:
            raise ValueError("Сессия неактивна.")
        if pin < 1 or pin > PIN_COUNT:
            raise ValueError("Пин должен быть от 1 до 8.")
        if state not in {"high", "low"}:
            raise ValueError("Состояние пина: high или low.")
        pins = list(session.pin_states or default_pin_states())
        if len(pins) < PIN_COUNT:
            pins = (pins + [False] * PIN_COUNT)[:PIN_COUNT]
        pins[pin - 1] = state == "high"
        commands = list(session.pending_commands or [])
        commands.append({"kind": "pin", "pin": pin, "state": state})
        session.pin_states = pins
        session.pending_commands = commands
        session.save(update_fields=["pin_states", "pending_commands", "updated_at"])
        broadcast_session(session)
        return session

    @staticmethod
    def enqueue_flash(*, session: StandSession, flash: UploadedFile) -> StandSession:
        if not session.is_active:
            raise ValueError("Сессия неактивна.")
        _require_svf(flash.name)
        session.pending_flash = flash
        session.pending_flash_name = flash.name
        commands = list(session.pending_commands or [])
        commands.append({"kind": "flash", "filename": flash.name})
        session.pending_commands = commands
        session.save(update_fields=["pending_flash", "pending_flash_name", "pending_commands", "updated_at"])
        broadcast_session(session)
        return session

    @staticmethod
    def consume_commands(session: StandSession) -> tuple[list[dict], bool]:
        commands = list(session.pending_commands or [])
        has_flash = session.pending_flash and any(cmd.get("kind") == "flash" for cmd in commands)
        session.pending_commands = []
        session.save(update_fields=["pending_commands", "updated_at"])
        return commands, bool(has_flash)
