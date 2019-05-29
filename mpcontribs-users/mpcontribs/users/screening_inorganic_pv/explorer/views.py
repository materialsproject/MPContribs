# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.shortcuts import render_to_response, redirect
from django.core.urlresolvers import reverse
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        API_KEY = user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint(request))
        from ..rest.rester import ScreeninginorganicpvRester
        with ScreeninginorganicpvRester(API_KEY, endpoint=ENDPOINT) as mpr:
            df = mpr.get_contributions()
            ctx['table'] = render_dataframe(df, webapp=True)
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("Screeninginorganicpv_explorer_index.html", ctx)
