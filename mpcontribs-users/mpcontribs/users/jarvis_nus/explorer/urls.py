import os
from django.conf.urls import url
from . import views

app_name = os.path.dirname(__file__).split(os.sep)[-2]
urlpatterns = [
    url(r'^$', views.index, name='index')
]
