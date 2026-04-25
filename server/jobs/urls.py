from django.urls import path

from .views import (
    AgentFirmwareDownloadView,
    AgentJobDetailView,
    AgentJobResultView,
    AgentNextJobView,
    ContinueAsGuestView,
    DashboardView,
    HomeView,
    JobDetailView,
    StartView,
)

app_name = "jobs"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("start/", StartView.as_view(), name="start"),
    path("continue-as-guest/", ContinueAsGuestView.as_view(), name="continue-as-guest"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("jobs/<uuid:pk>/", JobDetailView.as_view(), name="job-detail"),
    path("agent/api/jobs/claim/", AgentNextJobView.as_view(), name="agent-next-job"),
    path("agent/api/jobs/<uuid:job_id>/", AgentJobDetailView.as_view(), name="agent-job-detail"),
    path("agent/api/jobs/<uuid:job_id>/firmware/", AgentFirmwareDownloadView.as_view(), name="agent-job-firmware"),
    path("agent/api/jobs/<uuid:job_id>/result/", AgentJobResultView.as_view(), name="agent-job-result"),
]
