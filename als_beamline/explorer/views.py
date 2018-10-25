"""This module provides the views for the DTU explorer interface."""

import json, os
from bson import ObjectId
from django.shortcuts import render_to_response, redirect
from django.core.urlresolvers import reverse
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict

def index(request):
    from webtzite.models import RegisteredUser
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        from ..rest.rester import AlsBeamlineRester
        with AlsBeamlineRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                for typ in ['XAS', 'XMCD']:
                    html, divid = render_plot(mpr.get_all_spectra(typ), webapp=True)
                    ctx[typ] = {'html': html, 'divid': divid}
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("als_beamline_explorer_index.html", ctx)
