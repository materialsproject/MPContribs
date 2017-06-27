from django.conf.urls import include, url
from mpcontribs.user_modules import get_user_urlpatterns

urlpatterns = [
    url(r'', include('mpcontribs.portal.urls')),
    url(r'^rest/', include('mpcontribs.rest.urls')),
    url(r'^explorer/', include('mpcontribs.explorer.urls'))
] + [
    url(urlpattern[0], include(urlpattern[1]))
    for urlpattern in get_user_urlpatterns()
]
