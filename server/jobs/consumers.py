from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Job, PUBLIC_OWNER_USERNAME
from .services import JobService
from .views import get_guest_job_ids_from_cookies, is_guest_submission_enabled


class JobStatusConsumer(AsyncWebsocketConsumer):


    async def connect(self):
        self.job_id = self.scope["url_route"]["kwargs"]["job_id"]
        self.group_name = f"job_{self.job_id}"

        allowed = await self._check_access()
        if not allowed:
            
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

      
        payload = await self._get_current_payload()
        if payload is not None:
            await self.send(text_data=json.dumps(payload))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def job_update(self, event):
        """Обработчик сообщений с type="job.update", приходящих через
        channel_layer.group_send из JobService._broadcast_job_update."""
        await self.send(text_data=json.dumps(event["payload"]))

    @database_sync_to_async
    def _check_access(self) -> bool:
        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return Job.objects.filter(id=self.job_id, owner=user).exists()

        if not is_guest_submission_enabled():
            return False

        cookies = self.scope.get("cookies", {})
        guest_job_ids = get_guest_job_ids_from_cookies(cookies)
        return Job.objects.filter(
            id=self.job_id,
            id__in=guest_job_ids,
            owner__username=PUBLIC_OWNER_USERNAME,
        ).exists()

    @database_sync_to_async
    def _get_current_payload(self) -> dict | None:
        job = Job.objects.filter(id=self.job_id).select_related("claimed_by").first()
        if job is None:
            return None
        return JobService.serialize_job_status(job)