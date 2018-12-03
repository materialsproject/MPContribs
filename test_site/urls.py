"""test_site URL Configuration"""
from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    #url(r'', include('django_browserid.urls')),
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.urls')),
]
