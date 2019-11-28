from django.conf.urls import url
from mpcontribs.portal import views

app_name = 'mpcontribs_portal'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^(?P<cid>[\w\d]+)$', views.contribution, name='contribution'),
    url(r'^(?P<sid>[\w\d]+)\.cif$', views.cif, name='cif'),
    url(r'^(?P<cid>[\w\d]+)\.json$', views.download_json, name='json'),
]
