from __future__ import annotations

import json
import logging
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.signing import BadSignature
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, RedirectView, TemplateView

from .forms import JobUploadForm, RegistrationForm
from .models import Agent, Job, PUBLIC_OWNER_USERNAME
from .services import JobCompletion, JobService

logger = logging.getLogger("jobs")

GUEST_MODE_COOKIE = "guest_mode"
GUEST_JOBS_COOKIE = "guest_jobs"
GUEST_JOBS_COOKIE_SALT = "jobs.guest-history"
GUEST_HISTORY_MAX_ITEMS = 40
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def is_guest_submission_enabled() -> bool:
    return bool(getattr(settings, "ALLOW_ANON_JOB_SUBMISSION", True))


def _normalize_job_id(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _parse_guest_job_ids_payload(raw: str) -> list[str]:
    
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    normalized_ids: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, str):
            continue
        job_id = _normalize_job_id(item)
        if job_id is None or job_id in seen:
            continue
        seen.add(job_id)
        normalized_ids.append(job_id)
    return normalized_ids[-GUEST_HISTORY_MAX_ITEMS:]


def get_guest_job_ids(request: HttpRequest) -> list[str]:
    try:
        raw = request.get_signed_cookie(
            GUEST_JOBS_COOKIE,
            default="[]",
            salt=GUEST_JOBS_COOKIE_SALT,
        )
    except BadSignature:
        logger.warning("Подпись куки гостевых задач недействительна ip=%s", request.META.get("REMOTE_ADDR"))
        return []
    return _parse_guest_job_ids_payload(raw)


def get_guest_job_ids_from_cookies(cookies: dict) -> list[str]:
    
    fake_request = HttpRequest()
    fake_request.COOKIES = dict(cookies)
    return get_guest_job_ids(fake_request)


def set_guest_job_ids(response: HttpResponse, job_ids: list[str]) -> None:
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for item in job_ids:
        job_id = _normalize_job_id(item)
        if job_id is None or job_id in seen:
            continue
        seen.add(job_id)
        normalized_ids.append(job_id)

    payload = json.dumps(normalized_ids[-GUEST_HISTORY_MAX_ITEMS:])
    response.set_signed_cookie(
        GUEST_JOBS_COOKIE,
        payload,
        salt=GUEST_JOBS_COOKIE_SALT,
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


def mark_guest_mode(response: HttpResponse) -> None:
    response.set_cookie(
        GUEST_MODE_COOKIE,
        "1",
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


class HomeView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        guest_submission_enabled = is_guest_submission_enabled()
        if self.request.user.is_authenticated:
            return reverse("jobs:dashboard")
        if guest_submission_enabled and (
            self.request.COOKIES.get(GUEST_MODE_COOKIE) == "1" or get_guest_job_ids(self.request)
        ):
            return reverse("jobs:dashboard")
        return reverse("jobs:start")


class StartView(TemplateView):
    template_name = "registration/start.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("jobs:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allow_anonymous_submission"] = is_guest_submission_enabled()
        return context


class ContinueAsGuestView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        if not is_guest_submission_enabled():
            messages.error(request, "Анонимная отправка заданий отключена.")
            return redirect("jobs:start")
        response = redirect("jobs:dashboard")
        mark_guest_mode(response)
        logger.debug("Гостевой режим активирован ip=%s", request.META.get("REMOTE_ADDR"))
        return response


class RegisterView(FormView):
    form_class = RegistrationForm
    template_name = "registration/register.html"

    def form_valid(self, form: RegistrationForm) -> HttpResponse:
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Аккаунт создан.")
        logger.info("Зарегистрирован новый пользователь username=%s", user.username)
        return redirect("jobs:dashboard")


class DashboardView(FormView):
    form_class = JobUploadForm
    template_name = "jobs/dashboard.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated and not is_guest_submission_enabled():
            messages.error(request, "Анонимная отправка заданий отключена. Войдите в аккаунт.")
            return redirect("jobs:start")
        JobService.expire_timed_out_jobs()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: JobUploadForm) -> HttpResponse:
        if not self.request.user.is_authenticated and not is_guest_submission_enabled():
            messages.error(self.request, "Анонимная отправка заданий отключена. Войдите в аккаунт.")
            return redirect("jobs:start")
        firmware = form.cleaned_data["firmware"]
        is_guest = not self.request.user.is_authenticated
        owner = self.request.user if self.request.user.is_authenticated else JobService.get_public_owner()
        job = JobService.create_job(owner=owner, firmware=firmware)
        messages.success(self.request, f"Задача создана: {job.original_filename}")
        logger.info(
            "Задача загружена через форму job_id=%s owner=%s guest=%s ip=%s",
            job.id,
            owner.username,
            is_guest,
            self.request.META.get("REMOTE_ADDR"),
        )
        response = redirect(job.get_absolute_url())
        if is_guest:
            guest_job_ids = get_guest_job_ids(self.request)
            guest_job_ids.append(str(job.id))
            set_guest_job_ids(response, guest_job_ids)
            mark_guest_mode(response)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allow_anonymous_submission"] = is_guest_submission_enabled()
        if self.request.user.is_authenticated:
            jobs = self.request.user.jobs.select_related("claimed_by")
        else:
            guest_job_ids = get_guest_job_ids(self.request)
            jobs = Job.objects.filter(
                id__in=guest_job_ids,
                owner__username=PUBLIC_OWNER_USERNAME,
            ).select_related("claimed_by")
        context["jobs"] = jobs
        return context


class JobDetailView(DetailView):
    model = Job
    template_name = "jobs/job_detail.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated and not is_guest_submission_enabled():
            messages.error(request, "Анонимная отправка заданий отключена. Войдите в аккаунт.")
            return redirect("jobs:start")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        JobService.expire_timed_out_jobs()
        if self.request.user.is_authenticated:
            return self.request.user.jobs.select_related("claimed_by")
        guest_job_ids = get_guest_job_ids(self.request)
        return Job.objects.filter(
            id__in=guest_job_ids,
            owner__username=PUBLIC_OWNER_USERNAME,
        ).select_related("claimed_by")


class JobStatusView(View):
    

    def get(self, request: HttpRequest, pk) -> JsonResponse:
        if not request.user.is_authenticated and not is_guest_submission_enabled():
            return JsonResponse({"detail": "Forbidden"}, status=403)

        if request.user.is_authenticated:
            qs = request.user.jobs.select_related("claimed_by")
        else:
            guest_job_ids = get_guest_job_ids(request)
            qs = Job.objects.filter(
                id__in=guest_job_ids,
                owner__username=PUBLIC_OWNER_USERNAME,
            ).select_related("claimed_by")

        job = get_object_or_404(qs, pk=pk)
        return JsonResponse(JobService.serialize_job_status(job, request=request))


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
        return {
            "id": str(job.id),
            "status": job.status,
            "original_filename": job.original_filename,
            "download_url": request.build_absolute_uri(
                reverse("jobs:agent-job-firmware", kwargs={"job_id": job.id})
            ),
            "result_url": request.build_absolute_uri(
                reverse("jobs:agent-job-result", kwargs={"job_id": job.id})
            ),
            "detail_url": request.build_absolute_uri(
                reverse("jobs:agent-job-detail", kwargs={"job_id": job.id})
            ),
            "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
        }


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
        response = FileResponse(job.firmware.open("rb"), as_attachment=True, filename=job.original_filename)
        return response


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


class JobRetryView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk) -> HttpResponse:
        if not request.user.is_authenticated and not is_guest_submission_enabled():
            messages.error(request, "Анонимная отправка заданий отключена. Войдите в аккаунт.")
            return redirect("jobs:start")

        if request.user.is_authenticated:
            qs = request.user.jobs
        else:
            guest_job_ids = get_guest_job_ids(request)
            qs = Job.objects.filter(
                id__in=guest_job_ids,
                owner__username=PUBLIC_OWNER_USERNAME,
            )

        job = get_object_or_404(qs, pk=pk)

        try:
            new_job = JobService.retry_job(job=job, owner=job.owner)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(job.get_absolute_url())

        messages.success(request, f"Задача поставлена в очередь повторно ({new_job.retry_count}/{Job.MAX_RETRIES}).")
        logger.info(
            "Retry через UI original_job_id=%s new_job_id=%s user=%s",
            job.id,
            new_job.id,
            request.user if request.user.is_authenticated else "guest",
        )

        response = redirect(new_job.get_absolute_url())
        if not request.user.is_authenticated:
            guest_job_ids = get_guest_job_ids(request)
            guest_job_ids.append(str(new_job.id))
            set_guest_job_ids(response, guest_job_ids)
            mark_guest_mode(response)
        return response