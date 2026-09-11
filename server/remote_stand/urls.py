from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from jobs.spa import SpaView, spa_asset

urlpatterns = [
    path("admin/", admin.site.urls),
    path("assets/<path:path>", spa_asset),
    path("", include("jobs.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Клиентский роутер React: всё, что не API/агент/админка.
urlpatterns += [
    re_path(
        r"^(?!api/|agent/|admin/|media/|ws/|assets/).*$",
        SpaView.as_view(),
    ),
]
