import os

from django.core.wsgi import get_wsgi_application

from .env import load_env

load_env()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "remote_stand.settings")

application = get_wsgi_application()
