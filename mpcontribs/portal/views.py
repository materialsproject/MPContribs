"""This module provides the views for the portal."""

import os
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext
from django.core.urlresolvers import reverse
from mpcontribs.rest.views import get_endpoint
from mpcontribs.rest.rester import MPContribsRester

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        ctx.update({'alert': '{} authenticated'.format(user.email)})
        #ctx['landing_pages'] = []
        #rester = MPContribsRester(user.api_key, endpoint=get_endpoint(request))
        #for doc in rester.get_landing_pages():
        #    explorer = 'mpcontribs_users_{}_explorer_index'.format(doc['project'])
        #    entry = {'project': doc['project'], 'url': reverse(explorer)}
        #    content = doc['content']
        #    entry['title'] = content.get('title', doc['project'])
        #    authors = content.get('authors', 'No authors available.').split(',', 1)
        #    provenance = '<span class="pull-right" style="font-size: 13px;">{}'.format(authors[0])
        #    if len(authors) > 1:
        #        provenance += '''<button class="btn btn-sm btn-link" data-html="true"
        #        data-toggle="tooltip" data-placement="bottom" data-container="body"
        #        title="{}" style="padding: 0px 0px 2px 5px;">et al.</a>'''.format(
        #            authors[1].strip().replace(', ', '<br/>'))
        #        provenance += '</span>'
        #        entry['provenance'] = provenance
        #    ctx['landing_pages'].append(entry) # consider everything in DB released
    else:
        ctx.update({'alert': 'Please log in!'})
        #return redirect('{}?next={}'.format(reverse('cas_ng_login'), reverse('mpcontribs_portal_index')))
    return render_to_response("mpcontribs_portal_index.html", ctx)

def groupadd(request, token):
    if request.user.is_authenticated():
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
