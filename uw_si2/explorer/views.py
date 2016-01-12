"""This module provides the views for UW/SI2's explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.rester import MPContribsRester

def get_endpoint():
    from django.core.urlresolvers import reverse
    return reverse('mpcontribs_rest_index')[:-1]

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        print API_KEY, ENDPOINT
        #with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("uwsi2_explorer_index.html", locals(), ctx)
