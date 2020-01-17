#!/bin/sh
set -e

/venv/bin/python manage.py migrate --noinput

exec "$@"
