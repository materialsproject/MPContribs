# -*- coding: utf-8 -*-
"""This module provides the views for DiluteSoluteDiffusion's explorer interface."""

from __future__ import division, unicode_literals
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict
from mpcontribs.io.core.components import get_backgrid_table
from monty.json import jsanitize

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import DiluteSoluteDiffusionRester
        with DiluteSoluteDiffusionRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                prov = mpr.get_provenance()
                title = prov.pop('title')
                provenance = render_dict(prov, webapp=True)
                ranges, contribs = {}, []
                for host in mpr.get_hosts():
                    contribs.append({})
                    df = mpr.get_contributions(host)
                    contribs[-1]['table'] = get_backgrid_table(df)
                    contribs[-1]['formula'] = host
                    contribs[-1]['cid'] = 'test'
                    contribs[-1]['short_cid'] = 'test'
                    contribs[-1]['mp_id'] = 'test'

                    for col in df.columns:
                        if col == 'El.':
                            continue
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
                ranges = jsanitize(ranges)
                #contribs = jsanitize(contribs)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dilute_solute_diffusion_explorer_index.html", locals(), ctx)
