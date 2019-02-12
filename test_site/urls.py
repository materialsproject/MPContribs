"""test_site URL Configuration"""
from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.portal.urls')),
]
