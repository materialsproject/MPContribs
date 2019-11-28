import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.io.core.utils import get_short_object_id
from mpcontribs.users.utils import get_context
from mpcontribs.client import load_client
from mpcontribs.io.core.components.tdata import Table

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        ctx.update(get_context(project))
        client = load_client()
        ctx['contribs'] = []
        for contrib in client.contributions.get_entries(
            project=project, _fields=['id', 'identifier', 'data.formula']
        ).response().result['data']:
            contrib['formula'] = contrib['data'].pop('formula')
            contrib['short_cid'] = get_short_object_id(contrib['id'])
            ctx['contribs'].append(contrib)
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "dilute_solute_diffusion_index.html", ctx.flatten())
