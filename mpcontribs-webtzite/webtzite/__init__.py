import json
from django.conf import settings
from mpcontribs.client import load_client

def get_consumer(request):
    names = ['X-Consumer-Groups', 'X-Consumer-Username']
    headers = {}
    for name in names:
        key = f'HTTP_{name.upper().replace("-", "_")}'
        value = request.META.get(key)
        if value is not None:
            headers[name] = value
    return headers

def get_context(request, project):
    client = load_client(headers=get_consumer(request))
    prov = client.projects.get_entry(pk=project, _fields=['_all']).response().result

    ctx = {'project': project}
    ctx['project'] = project
    ctx['title'] = prov.pop('title')
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = prov['urls']
    other = prov.get('other', '')
    if other:
        ctx['other'] = json.dumps(other)
    if prov['columns']:
        ctx['columns'] = ['identifier', 'id'] + prov['columns']
        ctx['search_columns'] = ['identifier'] + [
            col for col in prov['columns'] if not col.endswith(']') and not col.endswith('CIF')
        ]

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
