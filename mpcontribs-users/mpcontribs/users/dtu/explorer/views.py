# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.shortcuts import render_to_response, redirect
try:
    from django.core.urlresolvers import reverse
except ImportError:
    from django.urls import reverse
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        from ..rest.rester import DtuRester
        with DtuRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                ctx['filters'] = {}
                filters = ['C']
                keys, subkeys = ['ΔE-KS', 'ΔE-QP'], ['indirect', 'direct']
                filters += ['_'.join([k, sk]) for k in keys for sk in subkeys]
                if request.method == 'POST':
                    ctx['filters'] = dict(
                        (f, map(float, request.POST['{}_slider'.format(f)].split(',')))
                        for f in filters
                    )
                df = mpr.get_contributions(bandgap_range=ctx['filters'])
                if request.method == 'GET':
                    for f in filters:
                        values = [float(v.split()[0]) for i,v in df[f.replace('_', '##')].iteritems()]
                        ctx['filters'][f] = [min(values), max(values)]
                ctx['nresults'] = df.shape[0]
                ctx['table'] = render_dataframe(df, webapp=True)
            except Exception as ex:
                ctx['alert'] = str(ex)
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("dtu_explorer_index.html", ctx)
