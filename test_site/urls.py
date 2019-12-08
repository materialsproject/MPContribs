from django.conf.urls import include, url
from django.views.generic.base import RedirectView
from webtzite import views

urlpatterns = [
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.portal.urls')),
    url(r'slac_mose2/', include('mpcontribs.users.slac_mose2.explorer.urls')),
    url(r'swf/', include('mpcontribs.users.swf.explorer.urls')),
    url(r'fe-co-v/', RedirectView.as_view(url='/swf', permanent=False)),
    url(r'fe-co-v/dataset-01', RedirectView.as_view(url='/swf', permanent=False)),
    url(r'als_beamline/', include('mpcontribs.users.als_beamline.explorer.urls')),
    url(r'dtu/', include('mpcontribs.users.dtu.explorer.urls')),
    url(r'carrier_transport/', include('mpcontribs.users.carrier_transport.explorer.urls')),
    url(r'boltztrap/', RedirectView.as_view(url='/carrier_transport', permanent=True)),
    url(r'screening_inorganic_pv/', include('mpcontribs.users.screening_inorganic_pv.explorer.urls')),
    url(r'Screeninginorganicpv/', RedirectView.as_view(url='/screening_inorganic_pv', permanent=False)),
    url(r'ScreeningInorganicPV/', RedirectView.as_view(url='/screening_inorganic_pv', permanent=False)),
    url(r'perovskites_diffusion/', include('mpcontribs.users.perovskites_diffusion.explorer.urls')),
    url(r'transparent_conductors/', include('mpcontribs.users.transparent_conductors.explorer.urls')),
    url(r'dilute_solute_diffusion/', include('mpcontribs.users.dilute_solute_diffusion.explorer.urls')),
    url(r'redox_thermo_csp/', include('mpcontribs.users.redox_thermo_csp.explorer.urls')),
    url(r'bioi_defects/', include('mpcontribs.users.bioi_defects.explorer.urls')),
    url(r'[a-zA-Z_]/', views.index)
]
