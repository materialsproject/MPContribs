from django.utils.functional import empty
from django.conf import settings
if settings._wrapped is empty:
    settings.configure()

from django.contrib import admin

from .models import DBConfig, RegisteredUser

admin.site.register(DBConfig)
admin.site.register(RegisteredUser)
