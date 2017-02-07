from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='MnO2_phase_selection_explorer_index'),
]
