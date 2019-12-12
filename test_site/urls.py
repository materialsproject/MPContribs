from django.conf.urls import include, url
from django.views.generic.base import RedirectView
from webtzite import views

urlpatterns = [
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.portal.urls')),

    # redirects
    url(r'^fe-co-v/?$', RedirectView.as_view(url='/swf/', permanent=False)),
    url(r'^fe-co-v/dataset-01/?$', RedirectView.as_view(url='/swf/', permanent=False)),
    url(r'^boltztrap/?$', RedirectView.as_view(url='/carrier_transport/', permanent=True)),
    url(r'^Screeninginorganicpv/?$', RedirectView.as_view(url='/screening_inorganic_pv/', permanent=False)),
    url(r'^ScreeningInorganicPV/?$', RedirectView.as_view(url='/screening_inorganic_pv/', permanent=False)),

    # default view
    url(r'^[a-zA-Z0-9_]{3,}/?$', views.index)
]
