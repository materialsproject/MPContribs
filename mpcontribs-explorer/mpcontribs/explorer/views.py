"""This module provides the views for the explorer interface."""

import json
from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse
from test_site.settings import swagger_client as client

def index(request):
    ctx = RequestContext(request)
    try:
        if request.method == 'GET':
            resp = client.projects.get_entries(mask=['project']).response()
            ctx['projects'] = [r.project for r in resp.result]

            #resp = swagger_client.contributions.get_contributions().response()
            #for contrib in resp.result:
            #    options[fields[0]].add(str(doc['identifier']))

            #    elif request.method == 'POST':
            #        projection_keys = ['mp_cat_id', 'project']
            #        options, selection = (
            #            dict(
            #                (field, [str(el) for el in json.loads(
            #                    request.POST['_'.join([prefix, field])]
            #                )]) for field in fields
            #            ) for prefix in ['options', 'selection']
            #        )

            #        mode = request.POST['submit']
            #        if mode == 'Find':
            #            criteria = {}
            #            for idx, key in enumerate(projection_keys):
            #                if selection[fields[idx]]:
            #                    criteria.update({
            #                        key: {'$in': selection[fields[idx]]}
            #                    })
            #            docs = mpr.query_contributions(criteria=criteria, limit=10)
            #            ctx['urls'] = [mpr.get_card(doc['_id'], embed=False) for doc in docs]
            #        elif mode == 'Show':
            #            if selection[fields[2]]:
            #                docs = mpr.query_contributions(
            #                    criteria={'_id': {'$in': selection[fields[2]]}}
            #                )
            #                ctx['urls'] = [mpr.get_card(doc['_id'], embed=False) for doc in docs]
            #            else:
            #                ctx.update({'alert': 'Enter a contribution identifier!'})
    except Exception as ex:
        ctx['alert'] = f'{ex}'

    return render(request, "mpcontribs_explorer_index.html", ctx.flatten())

def contribution(request, collection, cid):
    import nbformat
    from bson import ObjectId
    #from mpcontribs.builder import export_notebook
    material = {'detail_id': collection[:-1]}
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        with MPContribsRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
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
    return render_to_response("mpcontribs_explorer_contribution.html", ctx)

def cif(request, cid, structure_name):
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        with MPContribsRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            cif = mpr.get_cif(cid, structure_name)
            if cif:
                return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)

def download_json(request, collection, cid):
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        with MPContribsRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
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
