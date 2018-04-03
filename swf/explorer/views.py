"""This module provides the views for the SWF explorer interface."""

import os
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
from test_site.settings import STATIC_URL

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import SwfRester
        with SwfRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                df = mpr.get_contributions()
                ctx['table'] = render_dataframe(df, webapp=True)
                mod = os.path.dirname(__file__).split(os.sep)[-2]
                ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod])
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("swf_explorer_index.html", ctx)
