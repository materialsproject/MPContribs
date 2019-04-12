"""This module provides the views for the explorer interface."""

from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse
import nbformat
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from test_site.settings import swagger_client as client

def index(request):
    ctx = RequestContext(request)
    try:
        client.swagger_spec.config['use_models'] = True
        resp = client.projects.get_entries(mask=['project']).response()
        ctx['projects'] = [r.project for r in resp.result]
    except Exception as ex:
        ctx['alert'] = f'{ex}'
    return render(request, "mpcontribs_explorer_index.html", ctx.flatten())

def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = 'basic'
    body = html_exporter.from_notebook_node(nb)[0]
    soup = BeautifulSoup(body, 'html.parser')
    for t in soup.find_all('a', 'anchor-link'):
        t.extract() # rm anchors
    # mark cells with special name for toggling, and
    # make element id's unique by appending cid
    # NOTE every cell has only one tag with id
    div_name = None
    for div in soup.find_all('div', 'cell')[1:]:
        tag = div.find('h3', id=True)
        if tag is not None:
            tag['id'] = '-'.join([tag['id'], str(cid)])
            div_name = tag['id'].split('-')[0]
        if div_name is not None:
            div['name'] = div_name
    # name divs for toggling code_cells
    for div in soup.find_all('div', 'input'):
        div['name'] = 'Input'
    # separate script
    script = []
    for s in soup.find_all('script'):
        script.append(s.text)
        s.extract() # remove javascript
    return soup.prettify(), '\n'.join(script)

def contribution(request, cid):
    ctx = RequestContext(request)
    client.swagger_spec.config['use_models'] = False
    nb = client.notebooks.get_entry(cid=cid).response().result
    ctx['nb'], ctx['js'] = export_notebook(nb, cid)
    return render(request, "mpcontribs_explorer_contribution.html", ctx.flatten())

def cif(request, cid, structure_name):
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        with MPContribsRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            cif = mpr.get_cif(cid, structure_name)
            if cif:
                return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)

def download_json(request, collection, cid):
    import json
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        with MPContribsRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            contrib = mpr.find_contribution(cid, as_doc=True)
            if contrib:
                json_str = json.dumps(contrib)
                response = HttpResponse(json_str, content_type='application/json')
                response['Content-Disposition'] = 'attachment; filename={}.json'.format(cid)
                return response
    return HttpResponse(status=404)
