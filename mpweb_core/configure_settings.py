from django.conf import settings
if not settings.configured:
    from test_site import settings as test_site_settings
    settings.configure(test_site_settings)
