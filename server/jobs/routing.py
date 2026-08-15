from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/jobs/<uuid:job_id>/", consumers.JobStatusConsumer.as_asgi()),
]