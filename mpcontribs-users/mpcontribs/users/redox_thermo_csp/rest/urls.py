from django.conf.urls import url
from . import views
from mpcontribs.users_modules import get_user_explorer_name

name = get_user_explorer_name(__file__)

urlpatterns = [
    url(r'^rest/(?P<cid>[\w\d]+)/isobar$', views.isobar, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/isotherm$', views.isotherm, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/isoredox$', views.isoredox, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/enthalpy_dH$', views.enthalpy_dH, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/entropy_dS$', views.entropy_dS, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/ellingham$', views.ellingham, name=name),
    url(r'^rest/energy_analysis$', views.energy_analysis, name=name),
]
