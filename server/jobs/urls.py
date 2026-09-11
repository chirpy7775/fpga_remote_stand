from django.urls import path

from .api import (
    CsrfView,
    CurrentSessionView,
    JobDetailApiView,
    JobListCreateView,
    LoginView,
    LogoutView,
    MeView,
    PinMapView,
    RegisterView,
    ReleaseSessionView,
    SessionFlashView,
    SessionPinView,
    StandListView,
    TakeStandView,
)
from .monitor import MonitorJobDetailView, MonitorOverviewView
from .spa import HomeView
from .views import (
    AgentFirmwareDownloadView,
    AgentHeartbeatView,
    AgentInstructionDownloadView,
    AgentJobDetailView,
    AgentJobResultView,
    AgentNextJobView,
    AgentSessionFlashView,
    AgentSessionView,
)

app_name = "jobs"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("agent/api/heartbeat/", AgentHeartbeatView.as_view(), name="agent-heartbeat"),
    path("agent/api/session/", AgentSessionView.as_view(), name="agent-session"),
    path(
        "agent/api/session/<uuid:session_id>/flash/",
        AgentSessionFlashView.as_view(),
        name="agent-session-flash",
    ),
    path("agent/api/jobs/claim/", AgentNextJobView.as_view(), name="agent-next-job"),
    path("agent/api/jobs/<uuid:job_id>/", AgentJobDetailView.as_view(), name="agent-job-detail"),
    path("agent/api/jobs/<uuid:job_id>/firmware/", AgentFirmwareDownloadView.as_view(), name="agent-job-firmware"),
    path(
        "agent/api/jobs/<uuid:job_id>/instruction/",
        AgentInstructionDownloadView.as_view(),
        name="agent-job-instruction",
    ),
    path("agent/api/jobs/<uuid:job_id>/result/", AgentJobResultView.as_view(), name="agent-job-result"),
    path("api/auth/csrf/", CsrfView.as_view(), name="api-csrf"),
    path("api/auth/me/", MeView.as_view(), name="api-me"),
    path("api/auth/login/", LoginView.as_view(), name="api-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="api-logout"),
    path("api/auth/register/", RegisterView.as_view(), name="api-register"),
    path("api/stands/", StandListView.as_view(), name="api-stands"),
    path("api/stands/<int:pk>/take/", TakeStandView.as_view(), name="api-take-stand"),
    path("api/session/", CurrentSessionView.as_view(), name="api-session"),
    path("api/session/release/", ReleaseSessionView.as_view(), name="api-session-release"),
    path("api/session/pin/", SessionPinView.as_view(), name="api-session-pin"),
    path("api/session/flash/", SessionFlashView.as_view(), name="api-session-flash"),
    path("api/jobs/", JobListCreateView.as_view(), name="api-jobs"),
    path("api/jobs/<uuid:pk>/", JobDetailApiView.as_view(), name="api-job-detail"),
    path("api/pins/", PinMapView.as_view(), name="api-pins"),
    path("api/monitor/overview/", MonitorOverviewView.as_view(), name="api-monitor-overview"),
    path("api/monitor/jobs/<uuid:pk>/", MonitorJobDetailView.as_view(), name="api-monitor-job"),
]
