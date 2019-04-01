from django.conf.urls import url
from mpcontribs.explorer import views

app_name = 'mpcontribs_explorer'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    #url(r'^(?P<collection>[\w]+)$', views.index, name='collection'),
    #url(r'^(?P<collection>[\w]+)/(?P<cid>[\w\d]+)$',
    #    views.contribution, name='contribution'),
    #url(r'^materials/(?P<cid>[\w\d]+)/cif/(?P<structure_name>[\w]+)$',
    #    views.cif, name='cif'),
    #url(r'^(?P<collection>[\w]+)/(?P<cid>[\w\d]+).json$',
    #    views.download_json, name='contribution_json'),
]
