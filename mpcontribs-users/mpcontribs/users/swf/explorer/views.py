import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.users.utils import get_context

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        columns = ['Co', 'Fe', 'V', 'thickness', 'BH|max', 'Hc|MOKE', 'Hc|VSM']
        ctx.update(get_context(project, columns=columns))
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
