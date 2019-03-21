from django.conf.urls import url
from webtzite import views

app_name = 'webtzite'
urlpatterns = [
    url(r'^dashboard$', views.dashboard, name='dashboard'),
]
