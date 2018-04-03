"""This module provides the views for the jarvis_dft explorer interface."""

import os
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
        from ..rest.rester import JarvisDftRester
        with JarvisDftRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                tables = {}
                for typ in ['2d', '3d']:
                    df = mpr.get_contributions(typ)
                    tables[typ] = render_dataframe(df, webapp=True)
                ctx['tables'] = tables
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("jarvis_dft_explorer_index.html", ctx)
