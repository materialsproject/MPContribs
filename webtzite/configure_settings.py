import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_site.settings')
from django.conf import settings
if not settings.configured:
    from test_site import settings as test_site_settings
    settings.configure(test_site_settings)
