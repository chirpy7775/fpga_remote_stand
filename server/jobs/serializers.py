from __future__ import annotations

from django.utils import timezone

from .models import Agent, Job, TestbedSession


def _media_url(request, field) -> str | None:
    if not field:
        return None
    url = field.url
    if request is None:
        return url
    return request.build_absolute_uri(url)


def serialize_agent(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "status": agent.computed_status(),
        "online": agent.is_online,
        "last_seen_at": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
        "pin_map": agent.pin_map,
    }


def serialize_job(job: Job, request=None) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "status_display": job.get_status_display(),
        "original_filename": job.original_filename,
        "instruction_filename": job.instruction_filename,
        "target_agent": serialize_agent(job.target_agent) if job.target_agent else None,
        "claimed_by": str(job.claimed_by) if job.claimed_by else None,
        "queue_position": job.queue_position,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
        "execution_log": job.execution_log,
        "error_message": job.error_message,
        "result_video_url": _media_url(request, job.result_video),
    }


def serialize_session(session: TestbedSession, request=None) -> dict:
    remaining = max(0, int((session.ends_at - timezone.now()).total_seconds())) if session.is_active else 0
    return {
        "id": str(session.id),
        "token": session.token,
        "agent": serialize_agent(session.agent),
        "active": session.is_active,
        "started_at": session.started_at.isoformat(),
        "ends_at": session.ends_at.isoformat(),
        "remaining_seconds": remaining,
        "pin_states": list(session.pin_states or [False] * 8),
        "pending_flash_name": session.pending_flash_name,
        "pin_map": session.agent.pin_map,
    }


def serialize_agent_job(request, job: Job) -> dict:
    payload = {
        "id": str(job.id),
        "status": job.status,
        "original_filename": job.original_filename,
        "instruction_filename": job.instruction_filename,
        "download_url": request.build_absolute_uri(
            f"/agent/api/jobs/{job.id}/firmware/"
        ),
        "instruction_url": request.build_absolute_uri(
            f"/agent/api/jobs/{job.id}/instruction/"
        )
        if job.instruction
        else None,
        "result_url": request.build_absolute_uri(f"/agent/api/jobs/{job.id}/result/"),
        "detail_url": request.build_absolute_uri(f"/agent/api/jobs/{job.id}/"),
        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
    }
    return payload
