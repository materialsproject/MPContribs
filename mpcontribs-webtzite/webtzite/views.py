import os
from django.shortcuts import render
from django.template import RequestContext
from webtzite import get_context

def index(request):
    ctx = RequestContext(request)
    project = request.path.replace('/', '')
    try:
        ctx.update(get_context(request, project))
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
