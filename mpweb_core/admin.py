import mpweb_core.configure_settings
from django.contrib import admin
from .models import DBConfig, RegisteredUser

admin.site.register(DBConfig)
admin.site.register(RegisteredUser)
