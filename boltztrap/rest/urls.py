from django.conf.urls import url
from . import views
from mpcontribs.users_modules import get_user_explorer_name

name = get_user_explorer_name(__file__)
table_name = get_user_explorer_name(__file__, view='table')
eigs_name = get_user_explorer_name(__file__, view='eigenvalues')

urlpatterns = [
    url(r'^rest$', views.index, name=name),
    url(r'^rest/table$', views.table, name=table_name),
    url(r'^rest/table/(?P<db_type>[\w\d]+)$', views.table, name=table_name),
    url(r'^rest/eigenvalues/(?P<cid>[\w\d]+)$', views.eigenvalues, name=eigs_name),
    url(r'^rest/eigenvalues/(?P<cid>[\w\d]+)/(?P<db_type>[\w\d]+)$', views.eigenvalues, name=eigs_name),
    url(r'^rest/(?P<cid>[\w\d]+)$', views.index, name=name),
    url(r'^rest/(?P<cid>[\w\d]+)/(?P<db_type>[\w\d]+)$', views.index, name=name),
]

