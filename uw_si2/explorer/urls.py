from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='uwsi2_explorer_index'),
]
