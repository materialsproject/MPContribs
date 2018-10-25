"""This module provides the views for the SWF explorer interface."""

import os
from django.shortcuts import render_to_response, redirect
from django.core.urlresolvers import reverse
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
from test_site.settings import STATIC_URL, DEBUG

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        from ..rest.rester import SwfRester
        with SwfRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                df = mpr.get_contributions()
                ctx['table'] = render_dataframe(df, webapp=True)
                ctx['static_url'] = STATIC_URL
                if DEBUG:
                    mod = os.path.dirname(__file__).split(os.sep)[-2]
                    ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod])
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("swf_explorer_index.html", ctx)
