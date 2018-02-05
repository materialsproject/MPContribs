"""This module provides the views for the portal."""

import os
from importlib import import_module
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.users_modules import *
from mpcontribs.rest.views import get_endpoint
from test_site.settings import STATIC_URL

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        mod = os.path.dirname(__file__).split(os.sep)[-1]
        static_url = '_'.join([STATIC_URL[:-1], mod])
        a_tags = [[], []]
        for mod_path in get_users_modules():
            explorer = os.path.join(mod_path, 'explorer', 'apps.py')
            if os.path.exists(explorer):
                entry = {
                    'name': get_user_explorer_name(explorer),
                    'project': os.path.basename(mod_path)
                }
                mod_path_split = mod_path.split(os.sep)
                rester_path_split = mod_path_split[-4:] + ['rest', 'rester']
                rester_path = os.path.join(*rester_path_split)
                rester_path += '.py'
                idx = 1
                if os.path.exists(rester_path):
                    m = import_module('.'.join(rester_path_split[1:]))
                    UserRester = getattr(m, get_user_rester(mod_path_split[-1]))
                    endpoint = request.build_absolute_uri(get_endpoint())
                    r = UserRester(request.user.api_key, endpoint=endpoint)
                    docs = r.query_contributions(limit=1, projection={'content.title': 1})
                    if docs:
                        idx = int(not r.released)
                        entry['title'] = docs[0]['content'].get('title', entry['project'])
                    else:
                        idx = 1 # not released
                        entry['title'] = entry['project']
                a_tags[idx].append(entry)
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("mpcontribs_portal_index.html", locals(), ctx)
