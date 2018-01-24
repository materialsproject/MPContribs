"""This module provides the views for the SLAC MoSe2 explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.recdict import render_dict
from mpcontribs.io.core.components import render_plot

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import SlacMose2Rester
        with SlacMose2Rester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                provenance = render_dict(mpr.get_provenance(), webapp=True)
                graphs = {}
                for key, plot in mpr.get_graphs().items():
                    graphs[key] = render_plot(plot, webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("slac_mose2_explorer_index.html", locals(), ctx)
