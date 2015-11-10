from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='mpcontribs_rest_index'),
    url(r'^check_contributor$', views.check_contributor, name='check_contributor'),
    url(r'^submit$', views.submit_contribution, name='submit_contribution'),
    url(r'^build$', views.build_contribution, name='build_contribution'),
    url(r'^query$', views.query_contributions, name='query_contributions'),
    url(r'^delete$', views.delete_contributions, name='delete_contributions'),
    url(r'^collab$', views.update_collaborators, name='update_collaborators'),
]
