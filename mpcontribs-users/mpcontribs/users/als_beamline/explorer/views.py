import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.users.utils import get_context

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        #columns = ['formula', 'cid']
        #keys = RecursiveDict([
        #    ('composition', ['Co', 'Cu', 'Ce']),
        #    #('position', ['x', 'y']),
        #    ('XAS', ['min', 'max']),
        #    ('XMCD', ['min', 'max'])
        #])
        #columns += ['##'.join([k, sk]) for k, subkeys in keys.items() for sk in subkeys]
        ctx.update(get_context(project))
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
