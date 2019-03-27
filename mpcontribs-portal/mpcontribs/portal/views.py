"""This module provides the views for the portal."""

import os
from django.shortcuts import render
from django.template import RequestContext
from django.urls import reverse_lazy

from test_site.settings import DEBUG

from bravado.requests_client import RequestsClient
from bravado.client import SwaggerClient
from bravado.swagger_model import load_file

http_client = RequestsClient()
spec_dict = load_file('apispec.json', http_client=http_client)
# docker containers networking within docker-compose or Fargate task
host = 'api' if DEBUG else '127.0.0.1'
spec_dict['host'] = f'{host}:5000'
spec_dict['schemes'].append('http')
client = SwaggerClient.from_spec(
    spec_dict, http_client=http_client,
    config={'validate_responses': False}
)

def index(request):
    ctx = RequestContext(request)
    ctx['email'] = request.META.get('HTTP_X_CONSUMER_USERNAME')
    api_key = request.META.get('HTTP_X_CONSUMER_CUSTOM_ID')

    if api_key and ctx['email']:
        http_client.set_api_key(
            spec_dict['host'], b64decode(api_key),
            param_in='header', param_name='x-api-key'
        )
        ctx['landing_pages'] = []
        provenances = client.provenances.get_provenances().response().result
        for provenance in provenances:
            explorer = 'mpcontribs_users_{}_explorer_index'.format(provenance.project)
            entry = {'project': provenance.project, 'url': '#'}# TODO reverse(explorer)}
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

    return render(request, "mpcontribs_portal_index.html", ctx.flatten())
