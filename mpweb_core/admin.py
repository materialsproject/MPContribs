from django.conf import settings
settings.configure()

from django.contrib import admin

from .models import DBConfig, RegisteredUser

admin.site.register(DBConfig)
admin.site.register(RegisteredUser)
