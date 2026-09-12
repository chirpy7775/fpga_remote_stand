from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "assets/<path:path>",
        serve,
        {"document_root": settings.BASE_DIR / "frontend" / "dist" / "assets"},
    ),
    path("", include("jobs.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Маршруты клиентского роутера React. Неизвестные URL по-прежнему дают 404.
urlpatterns += [
    re_path(
        r"^(?:|login|register|results|monitor|docs/fpga|fpga(?:/session)?)/?$",
        TemplateView.as_view(template_name="index.html"),
    )
]
