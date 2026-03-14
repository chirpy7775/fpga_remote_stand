import os

from django.core.asgi import get_asgi_application

from .env import load_env

load_env()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "remote_stand.settings")

application = get_asgi_application()
