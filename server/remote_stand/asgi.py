import os

from .env import load_env

load_env()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "remote_stand.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

import jobs.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(jobs.routing.websocket_urlpatterns)
    ),
})