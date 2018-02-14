"""This module provides the views for the dlr_vieten explorer interface."""

import os
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import DlrVietenRester
        with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_index.html", ctx)

def tolerance_factors(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import DlrVietenRester
        with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                ionic_radii = render_dataframe(mpr.get_ionic_radii(), webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_tolerance_factors.html", ctx)
