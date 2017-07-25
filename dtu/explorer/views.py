"""This module provides the views for the DTU explorer interface."""

import json, os
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict
from test_site.settings import STATIC_URL
from ..rest.rester import DtuRester

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with DtuRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                provenance = render_dict(mpr.get_provenance(), webapp=True)
                table = render_dataframe(mpr.get_contributions(), webapp=True)
                mod = os.path.dirname(__file__).split(os.sep)[-2]
                static_url = '_'.join([STATIC_URL[:-1], mod])
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dtu_explorer_index.html", locals(), ctx)
