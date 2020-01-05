from django.conf.urls import url
from django.views.generic import TemplateView
from mpcontribs.portal import views

app_name = 'mpcontribs_portal'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^apply/?$', views.apply, name='apply'),
    url(r'^contribute/?$', TemplateView.as_view(template_name='mpcontribs_portal_contribute.html')),
    #url(r'^retrieve/?$', TODO),
    url(r'^(?P<project>[a-zA-Z0-9_]{3,}).csv$', views.csv, name='csv'),
    url(r'^(?P<cid>[a-f\d]{24})/?$', views.contribution, name='contribution'),
    url(r'^(?P<sid>[a-f\d]{24}).cif$', views.cif, name='cif'),
    url(r'^(?P<cid>[a-f\d]{24}).json$', views.download_json, name='json'),
]
