"""This module provides the views for the portal."""

import os
from django.shortcuts import render
from django.template import RequestContext
from django.urls import reverse_lazy
from test_site.settings import swagger_client as client

def index(request):
    ctx = RequestContext(request)
    ctx['landing_pages'] = []
    mask = ['project', 'title', 'authors']
    provenances = client.projects.get_entries(mask=mask).response().result
    for provenance in provenances:
        explorer = 'mpcontribs_users_{}_explorer_index'.format(provenance['project'])
        entry = {'project': provenance['project'], 'url': '#'}# TODO reverse(explorer)}
        entry['title'] = provenance['title']
        authors = provenance['authors'].split(',', 1)
        prov_display = f'<span class="pull-right" style="font-size: 13px;">{authors[0]}'
        if len(authors) > 1:
            prov_display += '''<button class="btn btn-sm btn-link" data-html="true"
            data-toggle="tooltip" data-placement="bottom" data-container="body"
            title="{}" style="padding: 0px 0px 2px 5px;">et al.</a>'''.format(
                authors[1].strip().replace(', ', '<br/>'))
            prov_display += '</span>'
            entry['provenance'] = prov_display
        ctx['landing_pages'].append(entry) # consider everything in DB released
    return render(request, "mpcontribs_portal_index.html", ctx.flatten())
