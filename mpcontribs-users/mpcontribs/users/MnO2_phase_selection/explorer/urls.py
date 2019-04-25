from django.conf.urls import url
from . import views

app_name = 'MnO2_phase_selection'
urlpatterns = [
    url(r'^$', views.index, name='index')
]
