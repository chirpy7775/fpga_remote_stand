from __future__ import annotations

import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger("jobs")


def _send(group: str, message: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, message)
    except Exception:
        logger.debug("Не удалось отправить в channel layer group=%s", group, exc_info=True)


def broadcast_job(job) -> None:
    from .serializers import serialize_job

    _send(
        f"job_{job.id}",
        {"type": "job.update", "payload": serialize_job(job)},
    )


def broadcast_session(session) -> None:
    from .serializers import serialize_session

    _send(
        f"session_{session.id}",
        {"type": "session.update", "payload": serialize_session(session)},
    )


def broadcast_camera_frame(*, agent_id: int, frame: bytes) -> None:
    _send(
        f"camera_agent_{agent_id}",
        {"type": "camera.frame", "frame": frame},
    )
