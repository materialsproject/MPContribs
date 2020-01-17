import os
import django_settings_file
from django.core.wsgi import get_wsgi_application

if 'DJANGO_SETTINGS_MODULE' in os.environ:
    os.environ.pop('DJANGO_SETTINGS_MODULE')  # required by django_settings_file

django_settings_file.setup()
application = get_wsgi_application()
