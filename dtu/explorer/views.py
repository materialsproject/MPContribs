"""This module provides the views for the DTU explorer interface."""

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
        from ..rest.rester import DtuRester
        with DtuRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                title = prov.pop('title')
                provenance = render_dict(prov, webapp=True)
                table = render_dataframe(mpr.get_contributions(), webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dtu_explorer_index.html", locals(), ctx)
