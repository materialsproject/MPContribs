"""This module provides the views for the MnO2_phase_selection explorer interface."""

from django.shortcuts import render
from django.template import RequestContext

def index(request):
    ctx = RequestContext(request)
    try:
        from mpcontribs.io.core.components import render_dataframe
        from mpcontribs.io.core.recdict import render_dict
        prov = mpr.get_provenance()
        ctx['title'] = prov.pop('title')
        ctx['provenance'] = render_dict(prov, webapp=True)
        tables = {}
        for phase in mpr.get_phases():
            df = mpr.get_contributions(phase=phase)
            tables[phase] = render_dataframe(df, webapp=True)
        ctx['tables'] = tables
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "MnO2_phase_selection_explorer_index.html", ctx.flatten())
