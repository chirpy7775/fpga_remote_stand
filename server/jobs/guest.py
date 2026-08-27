from __future__ import annotations

import json
import logging
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.core.signing import BadSignature
from django.http import HttpRequest, HttpResponse

from .models import Job

logger = logging.getLogger("jobs")

PUBLIC_OWNER_USERNAME = "public-upload"
GUEST_MODE_COOKIE = "guest_mode"
GUEST_JOBS_COOKIE = "guest_jobs"
GUEST_JOBS_COOKIE_SALT = "jobs.guest-history"
GUEST_HISTORY_MAX_ITEMS = 40
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def is_anon_enabled() -> bool:
    return bool(getattr(settings, "ALLOW_ANON_JOB_SUBMISSION", True))


def get_public_owner() -> User:
    user, created = User.objects.get_or_create(username=PUBLIC_OWNER_USERNAME)
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("Создан публичный пользователь username=%s", PUBLIC_OWNER_USERNAME)
    return user


def _normalize_job_id(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None


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
    response.set_cookie(
        GUEST_MODE_COOKIE,
        "1",
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


def jobs_for_request(request: HttpRequest):
    if request.user.is_authenticated:
        return request.user.jobs.select_related("claimed_by", "target_agent")
    if not is_anon_enabled():
        return None
    return Job.objects.filter(
        id__in=get_guest_job_ids(request),
        owner__username=PUBLIC_OWNER_USERNAME,
    ).select_related("claimed_by", "target_agent")


def owner_for_submit(request: HttpRequest) -> tuple[User | None, bool]:
    if request.user.is_authenticated:
        return request.user, False
    if not is_anon_enabled():
        return None, False
    return get_public_owner(), True
