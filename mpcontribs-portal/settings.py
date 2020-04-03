# -*- coding: utf-8 -*-
import os
from glob import glob
from django.conf.global_settings import *
from django_extensions.management.commands.generate_secret_key import (
    get_random_secret_key,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = get_random_secret_key()
NODE_ENV = os.environ.get("NODE_ENV", "production")
DEBUG = bool(NODE_ENV == "development")

ALLOWED_HOSTS = [
    os.environ.get("PORTAL_CNAME", "portal.mpcontribs.org"),
    "contribs.materialsproject.org",
    "jupyterhub.materialsproject.org",
    "localhost",
    "127.0.0.1",
    "127.0.0.2",
    "0.0.0.0",
    "docker.for.mac.localhost",
]
ALLOWED_HOSTS += ["10.0.{}.{}".format(i, j) for i in [10, 11] for j in range(256)]
ALLOWED_HOSTS += ["192.168.{}.{}".format(i, j) for i in range(10) for j in range(256)]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_extensions",
    "webpack_loader",
    "mpcontribs.portal",
]

MIDDLEWARE = (
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
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
