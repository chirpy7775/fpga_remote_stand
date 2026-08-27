from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/camera/exporter/", consumers.CameraExporterConsumer.as_asgi()),
    path("ws/camera/viewer/", consumers.CameraViewerConsumer.as_asgi()),
    path("ws/jobs/<uuid:job_id>/", consumers.JobStatusConsumer.as_asgi()),
    path("ws/session/", consumers.SessionStatusConsumer.as_asgi()),
]
