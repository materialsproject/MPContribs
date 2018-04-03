"""This module provides the views for the MnO2_phase_selection explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import Mno2PhaseSelectionRester
        with Mno2PhaseSelectionRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                tables = {}
                for phase in mpr.get_phases():
                    df = mpr.get_contributions(phase=phase)
                    tables[phase] = render_dataframe(df, webapp=True)
                ctx['tables'] = tables
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("MnO2_phase_selection_explorer_index.html", ctx)
