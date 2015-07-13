from django.conf.urls import *

urlpatterns = patterns(
    'rest.views',
    (r'^contribs/submit$', 'submit_contribution'),
    (r'^contribs/build$', 'build_contribution'),
    (r'^contribs/query$', 'query_contributions'),
    (r'^contribs/delete$', 'delete_contributions'),
    (r'^contribs/collab$', 'update_collaborators'),
)
