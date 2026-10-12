# -*- coding: utf-8 -*-
import os

from glob import glob
from django_extensions.management.commands.generate_secret_key import (
    get_random_secret_key,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = get_random_secret_key()
NODE_ENV = os.environ.get("NODE_ENV", "production")
DEBUG = bool(NODE_ENV == "development")

ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_extensions",
    "webpack_loader",
    "mpcontribs.portal",
]

MIDDLEWARE = (
    "mp_logging.django_ext.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "mpcontribs.portal.middleware.MyMiddleware",
)

ROOT_URLCONF = "mpcontribs.portal.urls"

path_glob = os.path.join(BASE_DIR, "mpcontribs", "users", "*", "explorer", "templates")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": glob(path_glob),
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "wsgi.application"
PROCESS_NAME = os.environ.get("SUPERVISOR_PROCESS_NAME", "default")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, f"{PROCESS_NAME}.sqlite3"),
    }
}


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATICFILES_DIRS = (os.path.join(BASE_DIR, "dist"),)

WEBPACK_LOADER = {
    "DEFAULT": {
        "CACHE": not DEBUG,
        "BUNDLE_DIR_NAME": "./",
        "STATS_FILE": os.path.join(BASE_DIR, "webpack-stats.json"),
    }
}

APPEND_SLASH = False
SECURE_REFERRER_POLICY = "unsafe-url"


def _logging_config():
    """Structured (Datadog JSON) logging, see `mp_logging`.

    Replaces Django's default handlers (its `django` / `django.server` loggers
    would otherwise also write plain text). The access log comes from
    gunicorn (gunicorn.conf.py).
    """
    from mp_logging import build_logging_config

    return build_logging_config(
        app_loggers=("mpcontribs",),
        debug=DEBUG,
        extra_loggers={
            # Django's own loggers: propagate to the root handler at INFO
            "django": {"level": "INFO", "handlers": [], "propagate": True},
            "django.server": {"level": "INFO", "handlers": [], "propagate": True},
        },
    )


LOGGING_CONFIG = "logging.config.dictConfig"
LOGGING = _logging_config()
