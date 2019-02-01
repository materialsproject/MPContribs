# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from bson.json_util import dumps
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.recdict import render_dict
from mpcontribs.io.core.components import render_plot

msg = 'Coming Soon! Contact <a href="mailto:mfucb@slac.stanford.edu">Ming-Fu Lu</a> for pre-publication access.'

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        if request.user.groups.filter(name='slac_mose2').exists():
            from webtzite.models import RegisteredUser
            user = RegisteredUser.objects.get(username=request.user.username)
            from ..rest.rester import SlacMose2Rester
            with SlacMose2Rester(user.api_key, endpoint=get_endpoint(request)) as mpr:
                try:
                    prov = mpr.get_provenance()
                    ctx['title'] = prov.pop('title')
                    ctx['provenance'] = render_dict(prov, webapp=True)

                    contribs = mpr.get_contributions()
                    ctx['graphs'], ctx['uuids'] = [], []
                    for plot in contribs['graphs']:
                        rplot = render_plot(plot, webapp=True)
                        ctx['graphs'].append(rplot[0])
                        ctx['uuids'].append(str(rplot[1]))

                    ctx['traces'] = dumps(contribs['traces'])
                    ctx['trace_names'] = [trace['name'] for trace in contribs['traces']]
                except Exception as ex:
                    ctx.update({'alert': str(ex)})
        else:
            ctx.update({'alert': msg})
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("slac_mose2_explorer_index.html", ctx)
