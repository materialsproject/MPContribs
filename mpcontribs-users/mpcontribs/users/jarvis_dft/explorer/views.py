import os
from django.shortcuts import render
from django.template import RequestContext
from test_site.settings import swagger_client as client
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components.tdata import Table

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        ctx['project'] = project
        prov = client.projects.get_entry(project=project).response().result
        prov.pop('id')
        ctx['title'] = prov.pop('title')
        ctx['provenance'] = RecursiveDict(prov).render()
        #    keys, subkeys = ['NUS', 'JARVIS'], ['id', 'Eₓ', 'CIF']
        #    columns = general_columns + ['##'.join([k, sk]) for k in keys for sk in subkeys]
        #    columns_jarvis = general_columns + ['id', 'E', 'ΔE|optB88vdW', 'ΔE|mbj', 'CIF']
        ctx['table'] = 'hello'
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
