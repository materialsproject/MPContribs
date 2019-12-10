import json
from django.conf import settings
from mpcontribs.client import load_client

def get_client_kwargs(request):
    name = 'X-Consumer-Groups'
    key = f'HTTP_{name.upper().replace("-", "_")}'
    value = request.META.get(key)
    return {'_request_options': {"headers": {name: value}}} if value else {}

def get_context(request, project):
    ctx = {'project': project}
    kwargs = get_client_kwargs(request)
    client = load_client()

    mask = ["title", "authors", "description", "urls", "other", "columns"]
    prov = client.projects.get_entry(pk=project, _fields=mask, **kwargs).response().result
    ctx['project'] = project
    ctx['title'] = prov.pop('title')
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = list(prov['urls'].values())
    ctx['other'] = json.dumps(prov.get('other'))
    ctx['columns'] = json.dumps([
        {'name': col, 'cell': 'uri', 'editable': 0}
        for col in ['identifier', 'id']
    ] + [
        {'name': col, 'cell': 'string', 'editable': 0} # 'nesting': nesting,
        for col in prov['columns']
    ])

    # TODO contribs key is only used in dilute_diffusion and should go through the table
    #from mpcontribs.io.core.utils import get_short_object_id
    #ctx['contribs'] = []
    #for contrib in client.contributions.get_entries(
    #    project=project, _fields=['id', 'identifier', 'data.formula']
    #).response().result['data']:
    #    formula = contrib.get('data', {}).get('formula')
    #    if formula:
    #        contrib['formula'] = formula
    #        contrib['short_cid'] = get_short_object_id(contrib['id'])
    #        ctx['contribs'].append(contrib)

    return ctx
