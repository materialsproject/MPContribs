"""This module provides the views for DiluteSoluteDiffusion's explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import get_backgrid_table
from monty.json import jsanitize
from ..rest.rester import DiluteSoluteDiffusionRester

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with DiluteSoluteDiffusionRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                contribs = mpr.get_contributions()
                if not contribs:
                    raise Exception('No contributions found for DiluteSoluteDiffusion Explorer!')
                ranges = {}
                for contrib in contribs:
                    df = contrib['table']
                    df.columns = list(df.columns[:-1]) + ['El.']
                    for col in df.columns[:-1]:
                        low, upp = min(df[col]), max(df[col])
                        if col == 'Z':
                            low -= 1
                            upp += 1
                        if col not in ranges:
                            ranges[col] = [low, upp]
                        else:
                            if low < ranges[col][0]:
                                ranges[col][0] = low
                            if upp > ranges[col][1]:
                                ranges[col][1] = upp
                    contrib['table'] = get_backgrid_table(df)
                ranges = jsanitize(ranges)
                contribs = jsanitize(contribs)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dilute_solute_diffusion_explorer_index.html", locals(), ctx)
