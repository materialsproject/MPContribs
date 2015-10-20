from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^accounts/profile/$', views.register, name='register'),
    url(r'^register$', views.register, name='register'),
]

