"""This module provides the views for the explorer interface."""

import json, nbformat
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponse
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.rest.views import get_endpoint
from mpcontribs.builder import export_notebook

def index(request):
    ctx = RequestContext(request)
    fields = ['identifiers', 'projects', 'cids']
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:

            if request.method == 'GET':
                options = dict((field, set()) for field in fields)
                docs = mpr.query_contributions()
                if docs:
                    for doc in docs:
                        options[fields[0]].add(str(doc['mp_cat_id']))
                        options[fields[1]].add(str(doc['project']))
                        options[fields[2]].add(str(doc['_id']))
                else:
                    ctx.update({'alert': 'No contributions available!'})
                options = dict((k, list(v)) for k,v in options.iteritems())
                selection = dict((field, []) for field in fields)

            elif request.method == 'POST':
                projection_keys = ['mp_cat_id', 'project']
                options, selection = (
                    dict(
                        (field, [str(el) for el in json.loads(
                            request.POST['_'.join([prefix, field])]
                        )]) for field in fields
                    ) for prefix in ['options', 'selection']
                )

                mode = request.POST['submit']
                if mode == 'Find':
                    criteria = {}
                    for idx, key in enumerate(projection_keys):
                        if selection[fields[idx]]:
                            criteria.update({
                                key: {'$in': selection[fields[idx]]}
                            })
                    docs = mpr.query_contributions(criteria=criteria, limit=10)
                    urls = [mpr.get_card(doc['_id'], embed=False) for doc in docs]
                elif mode == 'Show':
                    if selection[fields[2]]:
                        docs = mpr.query_contributions(
                            criteria={'_id': {'$in': selection[fields[2]]}}
                        )
                        urls = [mpr.get_card(doc['_id'], embed=False) for doc in docs]
                    else:
                        ctx.update({'alert': 'Enter a contribution identifier!'})

    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("mpcontribs_explorer_index.html", locals(), ctx)

def contribution(request, collection, cid):
    material = {'detail_id': collection[:-1]}
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                contrib = mpr.query_contributions(
                    criteria={'_id': cid}, projection={'build': 1}
                )[0]
                if 'build' in contrib and contrib['build']:
                    mpr.build_contribution(cid)
                    mpr.set_build_flag(cid, False)
                material = mpr.query_contributions(
                    criteria={'_id': ObjectId(cid)},
                    collection=collection, projection={'_id': 0}
                )[0]
            except IndexError:
                mpr.build_contribution(cid)
                material = mpr.query_contributions(
                    criteria={'_id': ObjectId(cid)},
                    collection=collection, projection={'_id': 0}
                )[0]
            material['nb'], material['nb_js'] = export_notebook(
                nbformat.from_dict(material['nb']), cid, separate_script=True
            )
            ctx.update({'material': jsanitize(material)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("mpcontribs_explorer_contribution.html", locals(), ctx)

def cif(request, cid, structure_name):
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
            cif = mpr.get_cif(cid, structure_name)
            if cif:
                return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)

def download_json(request, collection, cid):
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
            contrib = mpr.find_contribution(cid, as_doc=True)
            if contrib:
                json_str = json.dumps(contrib)
                response = HttpResponse(json_str, content_type='application/json')
                response['Content-Disposition'] = 'attachment; filename={}.json'.format(cid)
                return response
    return HttpResponse(status=404)

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
