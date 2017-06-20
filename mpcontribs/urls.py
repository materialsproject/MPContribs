from django.conf.urls import include, url

urlpatterns = [
    url(r'', include('mpcontribs.portal.urls')),
    url(r'^rest/', include('mpcontribs.rest.urls')),
    url(r'^explorer/', include('mpcontribs.explorer.urls')),
    url(r'^uwsi2/explorer/', include('mpcontribs.users.uw_si2.explorer.urls')),
    url(r'^MnO2_phase_selection/', include('mpcontribs.users.MnO2_phase_selection.explorer.urls')),
    url(r'^magics/mose2/', include('mpcontribs.users.slac_mose2.explorer.urls')),
]
