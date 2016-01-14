"""This module provides the views for UW/SI2's explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.explorer.views import get_endpoint
from monty.json import jsanitize
from ..rest.rester import UWSI2Rester

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with UWSI2Rester(API_KEY, endpoint=ENDPOINT) as mpr:
            contribs = jsanitize(mpr.get_uwsi2_contributions())
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("uwsi2_explorer_index.html", locals(), ctx)
