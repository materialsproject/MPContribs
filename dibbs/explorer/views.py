"""This module provides the views for the Dibbs explorer interface."""

import json, os
from bson import ObjectId
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
        from ..rest.rester import DibbsRester
        with DibbsRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                ctx['title'] = mpr.get_provenance().get('title')
                ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dibbs_explorer_index.html", ctx)
