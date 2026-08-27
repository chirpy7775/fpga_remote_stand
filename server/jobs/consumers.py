from __future__ import annotations

import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Agent, Job, StandSession
from .serializers import serialize_job, serialize_session
from .services import SessionService


def _query_param(scope, name: str) -> str | None:
    raw = scope.get("query_string", b"").decode("utf-8")
    values = parse_qs(raw).get(name) or parse_qs(raw).get("token")
    if not values:
        return None
    return values[0]


class CameraExporterConsumer(AsyncWebsocketConsumer):
    """Агент шлёт JPEG/PNG кадры. В группу не входит — только публикует."""

    async def connect(self):
        token = _query_param(self.scope, "token")
        agent = await _get_agent_by_token(token)
        if agent is None:
            await self.close(code=4401)
            return
        self.agent_id = agent.id
        self.group_name = f"camera_agent_{agent.id}"
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        if not bytes_data:
            return
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "camera.frame", "frame": bytes_data},
        )


class CameraViewerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = _query_param(self.scope, "token")
        session = await _get_active_session_by_token(token)
        if session is None:
            await self.close(code=4401)
            return
        self.group_name = f"camera_agent_{session.agent_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def camera_frame(self, event):
        frame = event.get("frame")
        if frame:
            await self.send(bytes_data=frame)


class JobStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        job_id = self.scope["url_route"]["kwargs"]["job_id"]
        user = self.scope.get("user")
        job = await _get_job_for_user(user, job_id)
        if job is None:
            await self.close(code=4403)
            return
        self.group_name = f"job_{job.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps(serialize_job(job)))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def job_update(self, event):
        await self.send(text_data=json.dumps(event["payload"]))


class SessionStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = _query_param(self.scope, "token")
        session = await _get_active_session_by_token(token)
        if session is None:
            await self.close(code=4401)
            return
        self.group_name = f"session_{session.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps(serialize_session(session)))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def session_update(self, event):
        await self.send(text_data=json.dumps(event["payload"]))


@database_sync_to_async
def _get_agent_by_token(token: str | None) -> Agent | None:
    if not token:
        return None
    return Agent.objects.filter(token=token, is_active=True).first()


@database_sync_to_async
def _get_active_session_by_token(token: str | None) -> StandSession | None:
    if not token:
        return None
    SessionService.expire_sessions()
    return (
        StandSession.objects.filter(token=token, released_at__isnull=True)
        .select_related("agent")
        .first()
    )


@database_sync_to_async
def _get_job_for_user(user, job_id) -> Job | None:
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return Job.objects.filter(id=job_id, owner=user).select_related("claimed_by", "target_agent").first()
