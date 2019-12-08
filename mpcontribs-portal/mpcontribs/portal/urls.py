from django.conf.urls import url
from mpcontribs.portal import views

app_name = 'mpcontribs_portal'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^(?P<cid>[a-f\d]{24})$', views.contribution, name='contribution'),
    url(r'^(?P<sid>[a-f\d]{24})\.cif$', views.cif, name='cif'),
    url(r'^(?P<cid>[a-f\d]{24})\.json$', views.download_json, name='json'),
]
