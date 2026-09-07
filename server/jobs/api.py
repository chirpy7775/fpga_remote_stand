from __future__ import annotations

import json
import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from .constants import PIN_MAP, SESSION_DURATION_SECONDS
from .guest import get_guest_job_ids, is_anon_enabled, jobs_for_request, owner_for_submit, set_guest_job_ids
from .lite_lang import InstructionError
from .models import Agent
from .serializers import serialize_agent, serialize_job, serialize_session
from .services import JobService, SessionService

logger = logging.getLogger("jobs")


def json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"detail": message}, status=status)


def user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
    }


class ApiAuthMixin:
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error("Нужна авторизация.", 401)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({"detail": "ok"})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        payload = user_payload(request.user) if request.user.is_authenticated else None
        return JsonResponse({"user": payload, "allow_anonymous": is_anon_enabled()})


class LoginView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        payload = _json_body(request)
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None:
            return json_error("Неверный логин или пароль.", 400)
        login(request, user)
        return JsonResponse({"user": user_payload(user)})


class LogoutView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        logout(request)
        return JsonResponse({"detail": "ok"})


class RegisterView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        payload = _json_body(request)
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        email = (payload.get("email") or "").strip()
        if not username or not password:
            return json_error("Укажите имя пользователя и пароль.")
        if User.objects.filter(username=username).exists():
            return json_error("Такой пользователь уже есть.")
        user = User.objects.create_user(username=username, password=password, email=email)
        login(request, user)
        return JsonResponse({"user": user_payload(user)}, status=201)


class StandListView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        if not request.user.is_authenticated and not is_anon_enabled():
            return json_error("Нужна авторизация.", 401)
        SessionService.expire_sessions()
        JobService.expire_timed_out_jobs()
        agents = Agent.objects.filter(is_active=True)
        return JsonResponse({"stands": [serialize_agent(agent) for agent in agents]})


class TakeStandView(ApiAuthMixin, View):
    def post(self, request: HttpRequest, pk: int) -> JsonResponse:
        agent = get_object_or_404(Agent, pk=pk, is_active=True)
        payload = _json_body(request)
        duration = payload.get("duration_seconds") or SESSION_DURATION_SECONDS
        try:
            duration = int(duration)
            session = SessionService.take(user=request.user, agent=agent, duration_seconds=duration)
        except (TypeError, ValueError) as exc:
            return json_error(str(exc), 409 if "занят" in str(exc) or "уже есть" in str(exc) else 400)
        return JsonResponse({"session": serialize_session(session, request)}, status=201)


class CurrentSessionView(ApiAuthMixin, View):
    def get(self, request: HttpRequest) -> JsonResponse:
        session = SessionService.active_for_user(request.user)
        if session is None:
            return JsonResponse({"session": None})
        return JsonResponse({"session": serialize_session(session, request)})


class ReleaseSessionView(ApiAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        session = SessionService.active_for_user(request.user)
        if session is None:
            return json_error("Нет активной сессии.", 404)
        SessionService.release(session)
        return JsonResponse({"session": serialize_session(session, request)})


class SessionPinView(ApiAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        session = SessionService.active_for_user(request.user)
        if session is None:
            return json_error("Нет активной сессии.", 404)
        payload = _json_body(request)
        try:
            pin = int(payload.get("pin"))
            state = str(payload.get("state", "")).lower()
            session = SessionService.enqueue_pin(session=session, pin=pin, state=state)
        except (TypeError, ValueError) as exc:
            return json_error(str(exc))
        return JsonResponse({"session": serialize_session(session, request)})


class SessionFlashView(ApiAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        session = SessionService.active_for_user(request.user)
        if session is None:
            return json_error("Нет активной сессии.", 404)
        flash = request.FILES.get("flash_file") or request.FILES.get("firmware")
        if flash is None:
            return json_error("Нужен файл прошивки.")
        try:
            session = SessionService.enqueue_flash(session=session, flash=flash)
        except ValueError as exc:
            return json_error(str(exc))
        return JsonResponse({"session": serialize_session(session, request)})


class JobListCreateView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        jobs = jobs_for_request(request)
        if jobs is None:
            return json_error("Нужна авторизация.", 401)
        JobService.expire_timed_out_jobs()
        return JsonResponse({"jobs": [serialize_job(job, request) for job in jobs]})

    def post(self, request: HttpRequest) -> JsonResponse:
        owner, is_guest = owner_for_submit(request)
        if owner is None:
            return json_error("Нужна авторизация.", 401)
        firmware = request.FILES.get("firmware") or request.FILES.get("flash_file")
        instruction = request.FILES.get("instruction") or request.FILES.get("instruction_file")
        agent_id = request.POST.get("target_agent") or request.POST.get("agent_id")
        if firmware is None or instruction is None or not agent_id:
            return json_error("Нужны прошивка .svf, инструкция .txt и стенд.")
        agent = get_object_or_404(Agent, pk=agent_id, is_active=True)
        try:
            job = JobService.create_job(
                owner=owner,
                firmware=firmware,
                instruction=instruction,
                target_agent=agent,
            )
        except InstructionError as exc:
            return json_error(str(exc))
        except ValueError as exc:
            return json_error(str(exc))
        response = JsonResponse({"job": serialize_job(job, request)}, status=201)
        if is_guest:
            guest_ids = get_guest_job_ids(request)
            guest_ids.append(str(job.id))
            set_guest_job_ids(response, guest_ids)
            logger.info("Гостевая задача создана job_id=%s", job.id)
        return response


class JobDetailApiView(View):
    def get(self, request: HttpRequest, pk) -> JsonResponse:
        jobs = jobs_for_request(request)
        if jobs is None:
            return json_error("Нужна авторизация.", 401)
        job = get_object_or_404(jobs, pk=pk)
        return JsonResponse({"job": serialize_job(job, request)})


class PinMapView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({"pins": PIN_MAP})


def _json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
