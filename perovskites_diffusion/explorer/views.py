"""This module provides the views for the PerovskitesDiffusion explorer interface."""

import json
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
        from ..rest.rester import PerovskitesDiffusionRester
        with PerovskitesDiffusionRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                ctx['abbreviations'] = render_dict(mpr.get_abbreviations(), webapp=True)
                ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("perovskites_diffusion_explorer_index.html", ctx)
