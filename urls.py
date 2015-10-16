from django.conf.urls import *

urlpatterns = patterns(
    'rest.views',
    (r'^mpfile/submit$', 'submit_mpfile'),
)
