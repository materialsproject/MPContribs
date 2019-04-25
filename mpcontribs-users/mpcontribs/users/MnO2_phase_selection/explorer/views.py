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
        data = client.contributions.get_table(project=project, per_page=3).response().result
        columns = list(data['items'][0].keys())
        table = Table(data['items'], columns=columns)
        ctx['table'] = table.render(project=project)
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
