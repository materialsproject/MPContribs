from django.conf.urls import include, url
from mpcontribs.users_modules import get_user_urlpatterns
from django.shortcuts import redirect

urlpatterns = [
    url(r'', include('mpcontribs.portal.urls')),
    url(r'^rest/', include('mpcontribs.rest.urls')),
    url(r'^explorer/', include('mpcontribs.explorer.urls')),
    url(r'^fe-co-v/dataset-01/', lambda request: redirect('mpcontribs_users_swf_explorer_index', permanent=True)),
    url(r'^boltztrap/', lambda request: redirect('mpcontribs_users_carrier_transport_explorer_index', permanent=True))
] + [
    url(urlpattern[0], include(urlpattern[1]))
    for urlpattern in get_user_urlpatterns()
]
