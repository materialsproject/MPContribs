"""This module provides the views for the explorer interface."""

import json
from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse
import nbformat
from base64 import b64decode
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from test_site.settings import swagger_client as client

def index(request):
    ctx = RequestContext(request)
    try:
        resp = client.projects.get_entries(mask=['project']).response()
        ctx['projects'] = [r['project'] for r in resp.result]
    except Exception as ex:
        ctx['alert'] = f'{ex}'
    api_key = request.META.get('HTTP_X_CONSUMER_CUSTOM_ID')
    if api_key:
        ctx['api_key'] = b64decode(api_key).decode('utf-8')
    return render(request, "mpcontribs_explorer_index.html", ctx.flatten())

def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = 'basic'
    body = html_exporter.from_notebook_node(nb)[0]
    soup = BeautifulSoup(body, 'html.parser')
    # mark cells with special name for toggling, and
    # TODO make element id's unique by appending cid
    for div in soup.find_all('div', 'output_wrapper'):
        tag = div.find('h2')
        div['name'] = tag.text.split()[0]
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
    nb = client.notebooks.get_entry(cid=cid).response().result
    ctx['nb'], ctx['js'] = export_notebook(nb, cid)
    return render(request, "mpcontribs_explorer_contribution.html", ctx.flatten())

def cif(request, cid, structure_name): # TODO
    #cif = mpr.get_cif(cid, structure_name)
    #if cif:
    #    return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)

def download_json(request, cid):
    contrib = client.contributions.get_entry(cid=cid).response().result
    if contrib:
        jcontrib = json.dumps(contrib)
        response = HttpResponse(jcontrib, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename={}.json'.format(cid)
        return response
    return HttpResponse(status=404)
