import re
import os
import django_settings_file
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

if 'DJANGO_SETTINGS_MODULE' in os.environ:
    os.environ.pop('DJANGO_SETTINGS_MODULE')  # required by django_settings_file

def immutable_file_test(path, url):
    # Match filename with 12 hex digits before the extension
    # e.g. app.db8f2edc0c8a.js
    return re.match(r'^.+\.[0-9a-f]{12}\..+$', url)

django_settings_file.setup()
application = get_wsgi_application()
application = WhiteNoise(
    application, root=os.path.dirname(__file__), immutable_file_test=immutable_file_test
)
