import django_settings_file
from django.core.wsgi import get_wsgi_application

django_settings_file.setup()
application = get_wsgi_application()
