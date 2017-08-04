"""This module provides the views for the MpWorkshop2017 explorer interface."""

import os
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
from ..rest.rester import MpWorkshop2017Rester

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with MpWorkshop2017Rester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                provenance = render_dict(prov, webapp=True)
                table = render_dataframe(mpr.get_contributions(), webapp=True)

            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("mp_workshop_2017_explorer_index.html", locals(), ctx)
