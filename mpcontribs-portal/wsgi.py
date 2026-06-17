# -*- coding: utf-8 -*-
import re
import os
import ddtrace.auto
import django_settings_file
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

if "DJANGO_SETTINGS_MODULE" in os.environ:
    os.environ.pop("DJANGO_SETTINGS_MODULE")  # required by django_settings_file


def immutable_file_test(path, url):
    # Match filename with 20 hex digits before the extension
    return re.match(r"^.+\.[0-9a-f]{20}\..+$", url) or re.match(
        r"^.+[0-9a-zA-Z_]{3,31}\.jpg$", url
    )


django_settings_file.setup()
application = get_wsgi_application()
application = WhiteNoise(
    application, root=os.path.dirname(__file__), immutable_file_test=immutable_file_test
)
