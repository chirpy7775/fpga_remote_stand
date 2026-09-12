from __future__ import annotations

import json
import logging

from django.http import FileResponse, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Agent, Job, TestbedSession
from .serializers import serialize_agent_job
from .services import JobCompletion, JobService, SessionService

logger = logging.getLogger("jobs")


@method_decorator(csrf_exempt, name="dispatch")
class AgentAuthMixin:
    agent: Agent | None = None

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.agent = self.authenticate(request)
        if self.agent is None:
            logger.warning(
                "Неудачная аутентификация агента ip=%s path=%s",
                request.META.get("REMOTE_ADDR"),
                request.path,
            )
            return JsonResponse({"detail": "Invalid agent token."}, status=401)
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def authenticate(request: HttpRequest) -> Agent | None:
        header = request.headers.get("Authorization", "")
        prefix = "Token "
        if header.startswith(prefix):
            token = header[len(prefix):].strip()
            if token:
                return Agent.objects.filter(token=token, is_active=True).first()
        return None


class AgentPayloadMixin:
    @staticmethod
    def serialize_job(request: HttpRequest, job: Job) -> dict:
        return serialize_agent_job(request, job)


class AgentNextJobView(AgentAuthMixin, AgentPayloadMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> JsonResponse:
        job = JobService.claim_next_job(agent=self.agent)
        if job is None:
            return JsonResponse({"job": None})
        logger.info("Агент получил задачу agent=%s job_id=%s", self.agent.pk, job.id)
        return JsonResponse({"job": self.serialize_job(request, job)})


class AgentJobDetailView(AgentAuthMixin, AgentPayloadMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id) -> JsonResponse:
        job = get_object_or_404(
            Job.objects.select_related("claimed_by", "owner").filter(claimed_by=self.agent),
            pk=job_id,
        )
        payload = self.serialize_job(request, job)
        payload.update(
            {
                "owner": job.owner.username,
                "log": job.execution_log,
                "error_message": job.error_message,
                "result_video_url": request.build_absolute_uri(job.result_video.url) if job.result_video else None,
            }
        )
        return JsonResponse(payload)


class AgentFirmwareDownloadView(AgentAuthMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id) -> FileResponse:
        job = get_object_or_404(Job.objects.filter(claimed_by=self.agent), pk=job_id)
        logger.debug("Агент скачивает прошивку job_id=%s agent=%s", job.id, self.agent.pk)
        return FileResponse(job.firmware.open("rb"), as_attachment=True, filename=job.original_filename)


class AgentJobResultView(AgentAuthMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, job_id) -> JsonResponse:
        job = get_object_or_404(Job.objects.filter(claimed_by=self.agent), pk=job_id)
        completion = JobCompletion(
            status=request.POST.get("status", Job.Status.ERROR),
            execution_log=request.POST.get("execution_log", ""),
            error_message=request.POST.get("error_message", ""),
        )
        completion.result_video = request.FILES.get("result_video")

        try:
            job = JobService.complete_job(job=job, agent=self.agent, completion=completion)
        except ValueError as exc:
            logger.warning("Ошибка завершения задачи job_id=%s agent=%s: %s", job_id, self.agent.pk, exc)
            return JsonResponse({"detail": str(exc)}, status=409)

        return JsonResponse({"id": str(job.id), "status": job.status})


class AgentHeartbeatView(AgentAuthMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> JsonResponse:
        SessionService.expire_sessions()
        JobService.expire_timed_out_jobs()
        try:
            payload = json.loads(request.body) if request.body and request.content_type == "application/json" else {}
            pins = payload.get("gpio_pins")
        except (ValueError, AttributeError):
            return JsonResponse({"detail": "Invalid heartbeat JSON."}, status=400)
        if pins is not None:
            if (not isinstance(pins, list) or len(pins) != 8
                    or any(type(pin) is not int or not 0 <= pin <= 53 for pin in pins)
                    or len(set(pins)) != 8):
                return JsonResponse({"detail": "GPIO_PINS must contain eight distinct BCM numbers (0–53)."}, status=400)
            if pins != self.agent.gpio_pins:
                self.agent.gpio_pins = pins
                self.agent.save(update_fields=["gpio_pins"])
        self.agent.touch()
        session = SessionService.active_for_agent(self.agent)
        return JsonResponse(
            {
                "status": self.agent.computed_status(),
                "has_session": session is not None,
            }
        )


class AgentSessionView(AgentAuthMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> JsonResponse:
        session = SessionService.active_for_agent(self.agent)
        self.agent.touch()
        if session is None:
            return JsonResponse({"session": None})
        commands, has_flash = SessionService.consume_commands(session)
        flash_url = None
        if has_flash and session.pending_flash:
            flash_url = request.build_absolute_uri(
                reverse("jobs:agent-session-flash", kwargs={"session_id": session.id})
            )
        return JsonResponse(
            {
                "session": {
                    "id": str(session.id),
                    "ends_at": session.ends_at.isoformat(),
                    "pin_states": session.pin_states,
                    "commands": commands,
                    "flash_url": flash_url,
                    "flash_name": session.pending_flash_name,
                }
            }
        )


class AgentSessionFlashView(AgentAuthMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest, session_id) -> FileResponse:
        session = get_object_or_404(
            TestbedSession.objects.filter(agent=self.agent),
            pk=session_id,
        )
        if not session.pending_flash:
            return JsonResponse({"detail": "Нет файла прошивки."}, status=404)
        filename = session.pending_flash_name or "session.svf"
        return FileResponse(session.pending_flash.open("rb"), as_attachment=True, filename=filename)


class AgentInstructionDownloadView(AgentAuthMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id) -> FileResponse:
        job = get_object_or_404(Job.objects.filter(claimed_by=self.agent), pk=job_id)
        if not job.instruction:
            return JsonResponse({"detail": "Нет файла инструкции."}, status=404)
        filename = job.instruction_filename or "instruction.txt"
        return FileResponse(job.instruction.open("rb"), as_attachment=True, filename=filename)
