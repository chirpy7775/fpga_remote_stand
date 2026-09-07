from __future__ import annotations

from datetime import timedelta

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from .guest import PUBLIC_OWNER_USERNAME
from .models import Agent, Job, StandSession
from .services import JobService, SessionService

RECENT_JOBS_LIMIT = 50


class StaffOnlyMixin:
    """Панель мониторинга доступна только персоналу."""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Нужна авторизация."}, status=401)
        if not request.user.is_staff:
            return JsonResponse({"detail": "Нужны права персонала."}, status=403)
        return super().dispatch(request, *args, **kwargs)


def _media_url(request: HttpRequest, field) -> str | None:
    return request.build_absolute_uri(field.url) if field else None


def _owner_label(job_or_session) -> tuple[str, bool]:
    username = job_or_session.owner.username
    is_guest = username == PUBLIC_OWNER_USERNAME
    return ("гость" if is_guest else username), is_guest


def _job_row(request: HttpRequest, job: Job) -> dict:
    owner, is_guest = _owner_label(job)
    return {
        "id": str(job.id),
        "status": job.status,
        "status_display": job.get_status_display(),
        "owner": owner,
        "is_guest": is_guest,
        "original_filename": job.original_filename,
        "instruction_filename": job.instruction_filename,
        "stand": job.target_agent.name if job.target_agent else None,
        "claimed_by": job.claimed_by.name if job.claimed_by else None,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": job.error_message,
        "firmware_url": _media_url(request, job.firmware),
        "instruction_url": _media_url(request, job.instruction),
        "result_video_url": _media_url(request, job.result_video),
    }


def _session_row(session: StandSession) -> dict:
    owner, is_guest = _owner_label(session)
    return {
        "id": str(session.id),
        "owner": owner,
        "is_guest": is_guest,
        "stand": session.agent.name,
        "started_at": session.started_at.isoformat(),
        "ends_at": session.ends_at.isoformat(),
        "remaining_seconds": max(0, int((session.ends_at - timezone.now()).total_seconds())),
        "pin_states": list(session.pin_states or []),
        "pending_flash_name": session.pending_flash_name,
    }


class MonitorOverviewView(StaffOnlyMixin, View):
    """Что происходит на стендах прямо сейчас плюс свежая история заявок."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> JsonResponse:
        SessionService.expire_sessions()
        JobService.expire_timed_out_jobs()

        agents = list(Agent.objects.all())
        sessions = list(
            StandSession.objects.filter(released_at__isnull=True, ends_at__gt=timezone.now())
            .select_related("agent", "owner")
        )
        running = list(
            Job.objects.filter(status=Job.Status.RUNNING)
            .select_related("owner", "target_agent", "claimed_by")
        )
        recent = list(
            Job.objects.select_related("owner", "target_agent", "claimed_by")
            .order_by("-created_at")[:RECENT_JOBS_LIMIT]
        )

        session_by_agent = {session.agent_id: session for session in sessions}
        job_by_agent = {job.claimed_by_id: job for job in running}

        stands = []
        for agent in agents:
            session = session_by_agent.get(agent.id)
            job = job_by_agent.get(agent.id)
            stands.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "status": agent.computed_status(),
                    "online": agent.is_online,
                    "is_active": agent.is_active,
                    "last_seen_at": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
                    "current_session": _session_row(session) if session else None,
                    "current_job": _job_row(request, job) if job else None,
                }
            )

        day_ago = timezone.now() - timedelta(days=1)
        return JsonResponse(
            {
                "generated_at": timezone.now().isoformat(),
                "totals": {
                    "stands": len(agents),
                    "online": sum(1 for agent in agents if agent.is_online),
                    "active_sessions": len(sessions),
                    "running_jobs": len(running),
                    "waiting_jobs": Job.objects.filter(status=Job.Status.WAITING).count(),
                    "jobs_last_day": Job.objects.filter(created_at__gte=day_ago).count(),
                    "errors_last_day": Job.objects.filter(
                        created_at__gte=day_ago, status=Job.Status.ERROR
                    ).count(),
                },
                "stands": stands,
                "sessions": [_session_row(session) for session in sessions],
                "jobs": [_job_row(request, job) for job in recent],
            }
        )


class MonitorJobDetailView(StaffOnlyMixin, View):
    """Полный лог одной заявки — отдельно, чтобы список оставался лёгким."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, pk) -> JsonResponse:
        job = get_object_or_404(
            Job.objects.select_related("owner", "target_agent", "claimed_by"), pk=pk
        )
        payload = _job_row(request, job)
        payload["execution_log"] = job.execution_log
        return JsonResponse({"job": payload})
