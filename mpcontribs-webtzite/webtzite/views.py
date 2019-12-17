import os
from django.shortcuts import render
from django.template import RequestContext, Context
from django.template.loader import select_template
from django.http.response import HttpResponse
from webtzite import get_context

def index(request):
    ctx = RequestContext(request)
    project = request.path.replace('/', '')

    try:
        ctx.update(get_context(request, project))
    except Exception as ex:
        ctx['alert'] = str(ex)

    templates = [f'{project}_index.html', 'explorer_index.html']
    template = select_template(templates)
    return HttpResponse(template.render(ctx.flatten(), request))
