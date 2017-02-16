"""test_site URL Configuration"""
from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    url(r'', include('django_browserid.urls')),
    url(r'', include('webtzite.urls')),
    url(r'^accounts/', include('nopassword.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^mpcontribs/', include('mpcontribs.urls')),
]
