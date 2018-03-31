from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='mpcontribs_rest_index'),
    url(r'^check_contributor$', views.check_contributor, name='check_contributor'),
    url(r'^check_contributor/(?P<db_type>[\w\d]+)$', views.check_contributor, name='check_contributor'),
    url(r'^submit$', views.submit_contribution, name='submit_contribution'),
    url(r'^submit/(?P<db_type>[\w\d]+)$', views.submit_contribution, name='submit_contribution'),
    url(r'^build$', views.build_contribution, name='build_contribution'),
    url(r'^build/(?P<db_type>[\w\d]+)$', views.build_contribution, name='build_contribution'),
    url(r'^query$', views.query_contributions, name='query_contributions'),
    url(r'^query/(?P<db_type>[\w\d]+)$', views.query_contributions, name='query_contributions'),
    url(r'^count$', views.count, name='count'),
    url(r'^count/(?P<db_type>[\w\d]+)$', views.count, name='count'),
    url(r'^delete$', views.delete_contributions, name='delete_contributions'),
    url(r'^delete/(?P<db_type>[\w\d]+)$', views.delete_contributions, name='delete_contributions'),
    url(r'^collab$', views.update_collaborators, name='update_collaborators'),
    url(r'^collab/(?P<db_type>[\w\d]+)$', views.update_collaborators, name='update_collaborators'),
    url(r'^cif/(?P<cid>[\w\d]+)/(?P<structure_name>[\w]+)$', views.cif, name='cif'),
    url(r'^cif/(?P<cid>[\w\d]+)/(?P<structure_name>[\w]+)/(?P<db_type>[\w\d]+)$', views.cif, name='cif'),
    url(r'^datasets/(?P<identifier>[-\w\d]+)$', views.datasets, name='datasets'),
    url(r'^datasets/(?P<identifier>[-\w\d]+)/(?P<db_type>[\w\d]+)$', views.datasets, name='datasets'),
    url(r'^card/(?P<cid>[\w\d]+)$', views.get_card, name='card'),
    url(r'^card/(?P<cid>[\w\d]+)/(?P<db_type>[\w\d]+)$', views.get_card, name='card'),
]
