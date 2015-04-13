from django.conf.urls import *

urlpatterns = patterns(
    'rest.views',
    (r'^mpfile/submit$', 'submit_mpfile'),
    (r'^contribs/query$', 'query_contribs'),
    (r'^contribs/delete$', 'delete_contribs'),
)
