from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.views import View
from django.views.generic import RedirectView


def frontend_index() -> Path:
    return Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"


def frontend_dist() -> Path:
    return Path(settings.BASE_DIR) / "frontend" / "dist"


class HomeView(RedirectView):
    """Собранный фронт отдаём с того же :8000, иначе кидаем на Vite."""

    def get(self, request: HttpRequest, *args, **kwargs):
        index = frontend_index()
        if index.is_file():
            return FileResponse(index.open("rb"), content_type="text/html")
        return super().get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return settings.FRONTEND_URL.rstrip("/") + "/"


SPA_PREFIXES = ("fpga", "login", "register", "results", "monitor", "docs")


class SpaView(View):
    """Клиентские маршруты React (/fpga, /login, …) — тот же index.html."""

    def get(self, request: HttpRequest, *args, **kwargs):
        rest = request.path.lstrip("/")
        if not any(rest == prefix or rest.startswith(prefix + "/") for prefix in SPA_PREFIXES):
            raise Http404()
        index = frontend_index()
        if not index.is_file():
            raise Http404("Фронт не собран. Запусти server/install.sh")
        return FileResponse(index.open("rb"), content_type="text/html")


def spa_asset(request: HttpRequest, path: str) -> HttpResponse:
    dist = frontend_dist().resolve()
    full = (dist / "assets" / path).resolve()
    if not str(full).startswith(str(dist / "assets")) or not full.is_file():
        raise Http404()
    return FileResponse(full.open("rb"))
