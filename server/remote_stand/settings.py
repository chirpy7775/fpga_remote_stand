from pathlib import Path
import os
import config as app_config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "remote_stand.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "remote_stand.wsgi.application"
ASGI_APPLICATION = "remote_stand.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "jobs:dashboard"
LOGOUT_REDIRECT_URL = "register"
EXECUTION_TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "300"))
ALLOW_ANON_JOB_SUBMISSION = app_config.ALLOW_ANON_JOB_SUBMISSION

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# В DEBUG-режиме пишем DEBUG+, в продакшне — INFO+
_APP_LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # Полный формат для файлов — время, уровень, имя логгера, pid, tid, сообщение
        "verbose": {
            "format": "{asctime} {levelname:<8} {name} pid={process} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        # Короткий формат для консоли
        "simple": {
            "format": "{asctime} {levelname:<8} {name} {message}",
            "style": "{",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        # --- Консоль (всегда активна) ---
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "DEBUG",
        },
        # --- Django: WARNING+, ротация по размеру 10 МБ, 5 архивов ---
        "django_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "django.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
            "level": "WARNING",
        },
        # --- HTTP-запросы: только ошибки (4xx/5xx) ---
        "request_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "requests.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
            "level": "WARNING",
        },
        # --- Безопасность: WARNING+, 10 архивов ---
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "security.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 10,
            "formatter": "verbose",
            "encoding": "utf-8",
            "level": "WARNING",
        },
        # --- Приложение jobs: DEBUG/INFO в зависимости от DEBUG-флага ---
        "jobs_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "jobs.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
            "level": _APP_LOG_LEVEL,
        },
    },
    "loggers": {
        # Корневой Django-логгер
        "django": {
            "handlers": ["console", "django_file"],
            "level": "WARNING",
            "propagate": False,
        },
        # HTTP-запросы (500-е попадают сюда)
        "django.request": {
            "handlers": ["console", "request_file"],
            "level": "WARNING",
            "propagate": False,
        },
        # CSRF, SuspiciousOperation и т.п.
        "django.security": {
            "handlers": ["console", "security_file"],
            "level": "WARNING",
            "propagate": False,
        },
        # Логика приложения
        "jobs": {
            "handlers": ["console", "jobs_file"],
            "level": _APP_LOG_LEVEL,
            "propagate": False,
        },
    },
}