from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='mpcontribs_portal_index'),
    url(r'^groupadd/(?P<token>\w+)$', views.groupadd, name='mpcontribs_portal_groupadd'),
]

