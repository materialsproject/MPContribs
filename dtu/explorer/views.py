# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json, nbformat
from bson import ObjectId
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
import collections as coll



def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import DtuRester
        with DtuRester(API_KEY, endpoint=ENDPOINT) as mpr:

            if request.method == 'GET':

                try:
                    prov = mpr.get_provenance()
                    title = prov.pop('title')
                    provenance = render_dict(prov, webapp=True)
                    table = render_dataframe(mpr.get_contributions(), webapp=True)
                except Exception as ex:
                    ctx.update({'alert': str(ex)})

            elif request.method == 'POST':
                ids = ['C_range', 'KS_ID_range', 'KS_D_range', 'QP_ID_range', 'QP_D_range']

                d = coll.OrderedDict([])
                d['C'] = coll.OrderedDict([])
                d['ΔE-KS'] = coll.OrderedDict([])
                d['ΔE-QP'] = coll.OrderedDict([])
                d['C'] = str(request.POST['C_range'])
                d['ΔE-KS']['indirect'] = str(request.POST['KS_ID_range'])
                d['ΔE-KS']['direct'] = str(request.POST['KS_D_range'])
                d['ΔE-QP']['indirect'] = str(request.POST['QP_ID_range'])
                d['ΔE-QP']['direct'] = str(request.POST['QP_D_range'])
                
                try:
                    prov = mpr.get_provenance()
                    title = prov.pop('title')
                    provenance = render_dict(prov, webapp=True)
                    table = render_dataframe(mpr.get_contributions(bandgap_range = d), webapp=True)
                except Exception as ex:
                    ctx.update({'alert': str(ex)})


    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dtu_explorer_index.html", locals(), ctx)
