import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.users.utils import get_context

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        keys, subkeys = ['NUS', 'JARVIS'], ['id', 'Eₓ', 'CIF']
        columns = ['.'.join([k, sk]) for k in keys for sk in subkeys]
        extra_keys = ['E', 'ΔE|optB88vdW', 'ΔE|mbj']
        columns += [f'JARVIS.{k}' for k in extra_keys]
        ctx.update(get_context(project, columns=sorted(columns)))
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
