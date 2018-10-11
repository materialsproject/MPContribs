from django.conf.urls import include, url
from mpcontribs.users_modules import get_user_urlpatterns
from django.shortcuts import redirect

urlpatterns = [
    url(r'', include('mpcontribs.portal.urls')),
    url(r'^(?i)rest/', include('mpcontribs.rest.urls')),
    url(r'^(?i)explorer/', include('mpcontribs.explorer.urls')),
    url(r'^(?i)fe-co-v/dataset-01/', lambda request: redirect('mpcontribs_users_swf_explorer_index', permanent=False))
] + [
    url(urlpattern[0], include(urlpattern[1]))
    for urlpattern in get_user_urlpatterns()
]
