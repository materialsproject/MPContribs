from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^check_contributor$', views.check_contributor, name='check_contributor'),
    url(r'^check_contributor/(?P<db_type>[\w\d]+)$', views.check_contributor, name='check_contributor'),
    url(r'^submit$', views.submit_contribution, name='submit_contribution'),
    url(r'^submit/(?P<db_type>[\w\d]+)$', views.submit_contribution, name='submit_contribution'),
    url(r'^query$', views.query_contributions, name='query_contributions'),
    url(r'^query/(?P<db_type>[\w\d]+)$', views.query_contributions, name='query_contributions'),
    url(r'^count$', views.count, name='count'),
    url(r'^count/(?P<db_type>[\w\d]+)$', views.count, name='count'),
    url(r'^delete$', views.delete_contributions, name='delete_contributions'),
    url(r'^delete/(?P<db_type>[\w\d]+)$', views.delete_contributions, name='delete_contributions'),
    url(r'^collab$', views.update_collaborators, name='update_collaborators'),
    url(r'^collab/(?P<db_type>[\w\d]+)$', views.update_collaborators, name='update_collaborators'),
    url(r'^datasets/(?P<identifier>[-\w\d]+)$', views.datasets, name='datasets'),
    url(r'^datasets/(?P<identifier>[-\w\d]+)/(?P<db_type>[\w\d]+)$', views.datasets, name='datasets'),
    url(r'^groupadd/(?P<token>\w+)$', views.groupadd, name='groupadd'),
    url(r'^groupadd/(?P<token>\w+)/(?P<db_type>[\w\d]+)$', views.groupadd, name='groupadd'),
]
