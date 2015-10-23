"""This module provides the views for the explorer interface."""

from test_site.settings import APPS
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.config import SITE
ENDPOINT = '/'.join([SITE, 'mpcontribs', 'rest'])

def index(request):
    API_KEY = request.user.api_key
    with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
        urls = [
            request.path + doc['_id']
            for doc in mpr.query_contributions(
                contributor_only=False, collection='compositions',
                projection={'_id': 1}
            )
        ]
    ctx = RequestContext(request, {'apps': APPS})
    return render_to_response("mpcontribs_explorer_index.html", locals(), ctx)

def composition(request, composition):
    API_KEY = request.user.api_key
    with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
        urls = [
            '/'.join([request.path, project, cid])
            for project, contribs in mpr.query_contributions(
                criteria={'_id': composition}, contributor_only=False,
                collection='compositions'
            )[0].iteritems() if project != '_id'
            for cid in contribs
        ]
    ctx = RequestContext(request, {'apps': APPS})
    return render_to_response("mpcontribs_explorer_index.html", locals(), ctx)

def contribution(request, composition, project, cid):
    if request.user.is_authenticated():
        material = {}
        API_KEY = request.user.api_key
        with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
            material['contributed_data'] = mpr.query_contributions(
                criteria={'_id': composition}, contributor_only=False,
                collection='compositions',
                projection={'_id': 0, '.'.join([project, cid]): 1}
            )[0][project][cid]
        material['pretty_formula'] = composition
    else:
        material = {k: composition for k in ['pretty_formula']}
    ctx = RequestContext(request, {'material': jsanitize(material), 'apps': APPS})
    return render_to_response("mpcontribs_explorer_composition.html", locals(), ctx)

# Instead of
# from monty.json import jsanitize
# use the following to fix UnicodeEncodeError
# and play nice with utf-8 encoding
from bson import SON
def jsanitize(obj):
    if isinstance(obj, (list, tuple)):
        return [jsanitize(i) for i in obj]
    elif isinstance(obj, dict):
        return SON([
            (unicode(k).encode('utf-8'), jsanitize(v))
            for k, v in obj.items()
        ])
    elif isinstance(obj, (int, float)):
        return obj
    elif obj is None:
        return None
    else:
        return unicode(obj).encode('utf-8')
