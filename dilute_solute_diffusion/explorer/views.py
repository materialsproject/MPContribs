# -*- coding: utf-8 -*-
"""This module provides the views for DiluteSoluteDiffusion's explorer interface."""

from __future__ import division, unicode_literals
from bson.json_util import dumps
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
from mpcontribs.io.core.components import get_backgrid_table
from mpcontribs.io.core.utils import get_short_object_id
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
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                ranges, contribs = {}, []

                for host in mpr.get_hosts():
                    contrib = {}
                    df = mpr.get_contributions(host)
                    contrib['table'] = render_dataframe(df, webapp=True)
                    contrib['formula'] = host
                    contrib.update(mpr.get_table_info(host))
                    contrib['short_cid'] = get_short_object_id(contrib['cid'])
                    contribs.append(contrib)

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

                ctx['ranges'] = dumps(ranges)
                ctx['contribs'] = contribs
            except Exception as ex:
                ctx['alert'] = str(ex)
    else:
        ctx['alert'] = 'Please log in!'
    return render_to_response("dilute_solute_diffusion_explorer_index.html", ctx)
