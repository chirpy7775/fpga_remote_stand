from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, FormView, RedirectView
from django.views.decorators.csrf import csrf_exempt

from .forms import JobUploadForm, RegistrationForm
from .models import Agent, Job
from .services import JobCompletion, JobService


class HomeView(RedirectView):
    pattern_name = "jobs:dashboard"

    def get_redirect_url(self, *args, **kwargs):
        return super().get_redirect_url(*args, **kwargs)


class RegisterView(FormView):
    form_class = RegistrationForm
    template_name = "registration/register.html"

    def form_valid(self, form: RegistrationForm) -> HttpResponse:
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Аккаунт создан.")
        return redirect("jobs:dashboard")


class DashboardView(LoginRequiredMixin, FormView):
    form_class = JobUploadForm
    template_name = "jobs/dashboard.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        JobService.expire_timed_out_jobs()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: JobUploadForm) -> HttpResponse:
        firmware = form.cleaned_data["firmware"]
        job = JobService.create_job(owner=self.request.user, firmware=firmware)
        messages.success(self.request, f"Задача создана: {job.original_filename}")
        return redirect(job.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["jobs"] = self.request.user.jobs.select_related("claimed_by")
        return context


class JobDetailView(LoginRequiredMixin, DetailView):
    model = Job
    template_name = "jobs/job_detail.html"

    def get_queryset(self):
        JobService.expire_timed_out_jobs()
        return self.request.user.jobs.select_related("claimed_by")


@method_decorator(csrf_exempt, name="dispatch")
class AgentAuthMixin:
    agent: Agent | None = None

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.agent = self.authenticate(request)
        if self.agent is None:
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
        agent, _ = Agent.objects.get_or_create(name="local-agent")
        return agent


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
        return JsonResponse({"job": self.serialize_job(request, job)})


class AgentJobDetailView(AgentAuthMixin, AgentPayloadMixin, View):
    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id) -> JsonResponse:
        job = get_object_or_404(Job.objects.select_related("claimed_by", "owner"), pk=job_id)
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
        job = get_object_or_404(Job, pk=job_id)
        if job.claimed_by_id != self.agent.id:
            raise Http404("Job is not assigned to this agent.")
        response = FileResponse(job.firmware.open("rb"), as_attachment=True, filename=job.original_filename)
        return response


class AgentJobResultView(AgentAuthMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, job_id) -> JsonResponse:
        job = get_object_or_404(Job, pk=job_id)
        completion = JobCompletion(
            status=request.POST.get("status", Job.Status.ERROR),
            execution_log=request.POST.get("execution_log", ""),
            error_message=request.POST.get("error_message", ""),
        )
        completion.result_video = request.FILES.get("result_video")

        try:
            job = JobService.complete_job(job=job, agent=self.agent, completion=completion)
        except ValueError as exc:
            return JsonResponse({"detail": str(exc)}, status=409)

        return JsonResponse({"id": str(job.id), "status": job.status})
