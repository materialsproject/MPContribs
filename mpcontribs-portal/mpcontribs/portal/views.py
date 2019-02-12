"""This module provides the views for the portal."""

import os
from django.shortcuts import render, redirect
from django.template import RequestContext
try:
    from django.core.urlresolvers import reverse
except ImportError:
    from django.urls import reverse
from test_site.settings import MPCONTRIBS_API_HOST, MPCONTRIBS_API_SPEC
from mpcontribs.rest.views import get_endpoint
from mpcontribs.rest.rester import MPContribsRester

from bravado.requests_client import RequestsClient
from bravado.client import SwaggerClient
from bravado.swagger_model import Loader

http_client = RequestsClient()
loader = Loader(http_client)
spec_dict = loader.load_spec(MPCONTRIBS_API_SPEC)

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated:
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        http_client.set_api_key(
            MPCONTRIBS_API_HOST, user.api_key,
            param_in='header', param_name='x-api-key'
        )
        client = SwaggerClient.from_spec(
            spec_dict, origin_url=MPCONTRIBS_API_SPEC, http_client=http_client,
            config={'validate_responses': False}
        )

        ctx['landing_pages'] = []
        provenances = client.provenances.get_provenances().response().result
        for provenance in provenances:
            explorer = 'mpcontribs_users_{}_explorer_index'.format(provenance.project)
            entry = {'project': provenance.project, 'url': reverse(explorer)}
            entry['title'] = provenance.title
            authors = provenance.authors.split(',', 1)
            prov_display = '<span class="pull-right" style="font-size: 13px;">{}'.format(authors[0])
            if len(authors) > 1:
                prov_display += '''<button class="btn btn-sm btn-link" data-html="true"
                data-toggle="tooltip" data-placement="bottom" data-container="body"
                title="{}" style="padding: 0px 0px 2px 5px;">et al.</a>'''.format(
                    authors[1].strip().replace(', ', '<br/>'))
                prov_display += '</span>'
                entry['provenance'] = prov_display
            ctx['landing_pages'].append(entry) # consider everything in DB released
    else:
        ctx.update({'alert': 'Please log in!'})
        #return redirect('{}?next={}'.format(reverse('webtzite:cas_ng_login'), reverse('mpcontribs_portal_index')))
    return render(request, "mpcontribs_portal_index.html", ctx.flatten())

def groupadd(request, token):
    if request.user.is_authenticated:
        from webtzite.models import RegisteredUser
        from mpcontribs.rest.rester import MPContribsRester
        user = RegisteredUser.objects.get(username=request.user.username)
        r = MPContribsRester(user.api_key, endpoint=get_endpoint(request))
        r.groupadd(token)
        return redirect(reverse('mpcontribs_portal_index'))
    else:
        return redirect('{}?next={}'.format(
            reverse('cas_ng_login'),
            reverse('mpcontribs_portal_groupadd', kwargs={'token': token})
        ))
