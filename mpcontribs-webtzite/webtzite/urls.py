from django.conf.urls import include, url
from django.urls import path
from django.contrib import admin
admin.autodiscover()
from webtzite import views

app_name = 'webtzite'
urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^dashboard$', views.dashboard, name='dashboard'),
]
