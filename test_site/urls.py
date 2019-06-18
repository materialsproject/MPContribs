from django.conf.urls import include, url
from django.views.generic.base import RedirectView

urlpatterns = [
    url(r'', include('webtzite.urls')),
    url(r'', include('mpcontribs.portal.urls')),
    url(r'explorer/', include('mpcontribs.explorer.urls')),
    url(r'MnO2_phase_selection/', include('mpcontribs.users.MnO2_phase_selection.explorer.urls')),
    url(r'jarvis_nus/', include('mpcontribs.users.jarvis_nus.explorer.urls')),
    url(r'defect_genome_pcfc_materials/', include('mpcontribs.users.defect_genome_pcfc_materials.explorer.urls')),
    url(r'slac_mose2/', include('mpcontribs.users.slac_mose2.explorer.urls')),
    url(r'swf/', include('mpcontribs.users.swf.explorer.urls')),
    url(r'fe-co-v/', RedirectView.as_view(url='/swf', permanent=False)),
    url(r'fe-co-v/dataset-01', RedirectView.as_view(url='/swf', permanent=False)),
    url(r'als_beamline/', include('mpcontribs.users.als_beamline.explorer.urls')),
    url(r'dtu/', include('mpcontribs.users.dtu.explorer.urls')),
    url(r'carrier_transport/', include('mpcontribs.users.carrier_transport.explorer.urls')),
    url(r'screening_inorganic_pv/', include('mpcontribs.users.screening_inorganic_pv.explorer.urls')),
    url(r'Screeninginorganicpv/', RedirectView.as_view(url='/screening_inorganic_pv', permanent=False)),
    url(r'perovskites_diffusion/', include('mpcontribs.users.perovskites_diffusion.explorer.urls')),
    url(r'transparent_conductors/', include('mpcontribs.users.transparent_conductors.explorer.urls')),
    url(r'dilute_solute_diffusion/', include('mpcontribs.users.dilute_solute_diffusion.explorer.urls')),
]
