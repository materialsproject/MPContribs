"""This module provides the views for the portal."""

import os
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext
from django.core.urlresolvers import reverse
from mpcontribs.users_modules import *
from mpcontribs.rest.views import get_endpoint
from test_site.settings import STATIC_URL#, PROXY_URL_PREFIX

def index(request):
    from webtzite.models import RegisteredUser
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        mod = os.path.dirname(__file__).split(os.sep)[-1]
        jpy_user = os.environ.get('JPY_USER')
        ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod]) if jpy_user else STATIC_URL[:-1]
        ctx['a_tags'] = [[], []]
        for mod_path in get_users_modules():
            explorer = os.path.join(mod_path, 'explorer', 'apps.py')
            dash_app_exists = os.path.exists(os.path.join(mod_path, 'dash_app.py'))
            if os.path.exists(explorer) or dash_app_exists:
                entry = {'project': os.path.basename(mod_path)}
                #entry['url'] = os.path.join(PROXY_URL_PREFIX, mod_path.split(os.sep)[-1]) if dash_app_exists else
                entry['url'] = reverse(get_user_explorer_name(explorer))
                idx = 1
                UserRester = get_user_rester(mod_path)
                if UserRester is not None:
                    r = UserRester(user.api_key, endpoint=get_endpoint(request))
                    docs = r.query_contributions(
                        limit=1, projection={'content.title': 1, 'content.authors': 1}
                    )
                    if docs:
                        idx = int(not r.released)
                        content = docs[0]['content']
                        entry['title'] = content.get('title', entry['project'])
                        authors = content.get('authors', 'No authors available.').split(',', 1)
                        provenance = '<span class="pull-right" style="font-size: 13px;">{}'.format(authors[0])
                        if len(authors) > 1:
                            provenance += '''<button class="btn btn-sm btn-link" data-html="true"
                            data-toggle="tooltip" data-placement="bottom" data-container="body"
                            title="{}" style="padding: 0px 0px 2px 5px;">et al.</a>'''.format(
                                    authors[1].strip().replace(', ', '<br/>'))
                        provenance += '</span>'
                        entry['provenance'] = provenance
                    else:
                        idx = 1 # not released
                        entry['title'] = entry['project']
                if not idx or (idx and 'jupyterhub' in get_endpoint(request)):
                    ctx['a_tags'][idx].append(entry)
    else:
        ctx.update({'alert': 'Please log in! MONGO_URI: {}'.format(os.environ.get(MONGO_URI))})
        #return redirect('{}?next={}'.format(reverse('cas_ng_login'), reverse('mpcontribs_portal_index')))
    return render_to_response("mpcontribs_portal_index.html", ctx)

def groupadd(request, token):
    from webtzite.models import RegisteredUser
    from mpcontribs.rest.rester import MPContribsRester
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        r = MPContribsRester(user.api_key, endpoint=get_endpoint(request))
        r.groupadd(token)
        return redirect(reverse('mpcontribs_portal_index'))
    else:
        return redirect('{}?next={}'.format(
            reverse('cas_ng_login'),
            reverse('mpcontribs_portal_groupadd', kwargs={'token': token})
        ))
