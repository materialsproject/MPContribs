import json
from django.conf import settings
from mpcontribs.client import load_client
from mpcontribs.io.core.components.hdata import HierarchicalData
# TODO should not be needed if render_json.js took care of display/unit/value

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
    prov = client.projects.get_entry(pk=project, _fields=['_all']).result()

    ctx = {'project': project}
    ctx['project'] = project
    long_title = prov.get('long_title')
    ctx['title'] = long_title if long_title else prov['title']
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = prov['urls']
    other = prov.get('other', '')
    if other:
        ctx['other'] = json.dumps(HierarchicalData(other))
    if prov['columns']:
        ctx['columns'] = ['identifier', 'id', 'formula'] + list(prov['columns'].keys())
        ctx['search_columns'] = ['identifier', 'formula'] + [
            col for col in prov['columns'].keys() if not col.endswith(']') and not col.endswith('CIF')
        ]
        ctx['ranges'] = json.dumps(prov['columns'])

    # TODO contribs key is only used in dilute_diffusion and should go through the table
    #from mpcontribs.io.core.utils import get_short_object_id
    #ctx['contribs'] = []
    #for contrib in client.contributions.get_entries(
    #    project=project, _fields=['id', 'identifier', 'data.formula']
    #).result()['data']:
    #    formula = contrib.get('data', {}).get('formula')
    #    if formula:
    #        contrib['formula'] = formula
    #        contrib['short_cid'] = get_short_object_id(contrib['id'])
    #        ctx['contribs'].append(contrib)

    return ctx
