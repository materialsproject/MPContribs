from django.conf.urls import include, url

urlpatterns = [
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.portal.urls')),
    url(r'explorer/', include('mpcontribs.explorer.urls')),
    url(r'MnO2_phase_selection/', include('mpcontribs.users.MnO2_phase_selection.explorer.urls')),
]
