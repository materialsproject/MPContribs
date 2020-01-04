"""This module provides the views for the portal."""

import os
import json
import nbformat
from time import sleep
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from fido.exceptions import HTTPTimeoutError
from pandas.io.json._normalize import nested_to_record
from pandas import DataFrame
from hendrix.experience import crosstown_traffic, hey_joe

from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse
from django.urls import reverse

from mpcontribs.client import load_client
from webtzite import get_consumer

def index(request):
    ctx = RequestContext(request)
    ctx['landing_pages'] = []
    mask = ['project', 'title', 'authors']
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    provenances = client.projects.get_entries(_fields=mask).response().result
    for provenance in provenances['data']:
        entry = {'project': provenance['project']}
        img_path = os.path.join(os.path.dirname(__file__), 'assets', 'images', provenance['project'] + '.jpg')
        if not os.path.exists(img_path):
            entry['contribs'] = client.contributions.get_entries(
                project=provenance['project'] # default limit 20
            ).response().result['data']
        entry['title'] = provenance['title']
        authors = provenance['authors'].split(',', 1)
        prov_display = f'<br><span style="font-size: 13px;">{authors[0]}'
        if len(authors) > 1:
            prov_display += '''<button class="btn btn-sm btn-link" data-html="true"
            data-toggle="tooltip" data-placement="bottom" data-container="body"
            title="{}" style="padding: 0px 0px 2px 5px;">et al.</a>'''.format(
                authors[1].strip().replace(', ', '<br/>'))
            prov_display += '</span>'
        entry['provenance'] = prov_display
        ctx['landing_pages'].append(entry)  # visibility governed by is_public flag and X-Consumer-Groups header
    return render(request, "mpcontribs_portal_index.html", ctx.flatten())


def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = 'basic'
    body = html_exporter.from_notebook_node(nb)[0]
    soup = BeautifulSoup(body, 'html.parser')
    # mark cells with special name for toggling, and
    # TODO make element id's unique by appending cid (for ingester)
    for div in soup.find_all('div', 'output_wrapper'):
        script = div.find('script')
        if script:
            script = script.contents[0]
            if script.startswith('render_json'):
                div['name'] = 'HData'
            elif script.startswith('render_table'):
                div['name'] = 'Table'
            elif script.startswith('render_plot'):
                div['name'] = 'Graph'
        else:
            pre = div.find('pre')
            if pre and pre.contents[0].startswith('Structure'):
                div['name'] = 'Structure'
    # name divs for toggling code_cells
    for div in soup.find_all('div', 'input'):
        div['name'] = 'Code'
    # separate script
    script = []
    for s in soup.find_all('script'):
        script.append(s.text)
        s.extract()  # remove javascript
    return soup.prettify(), '\n'.join(script)


def contribution(request, cid):
    ctx = RequestContext(request)
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    nb = client.notebooks.get_entry(pk=cid).response().result  # generate notebook with cells

    if not nb['cells'][-1]['outputs']:
        dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>'
        ctx['alert'] = f'Detail page is building in the background {dots}'

        @crosstown_traffic()
        def execute_cells():
            nb = client.notebooks.get_entry(pk=cid).response().result  # execute cells
            hey_joe.broadcast(f'Done. Reloading page {dots}')

        @crosstown_traffic()
        def heartbeat():
            interval = 15
            for i in range(4):
                sleep(interval)
                hey_joe.broadcast(f'Still building after {(i+1)*interval} seconds {dots}')
            hey_joe.broadcast(f'Giving up after {(i+1)*interval} seconds. Come back later.')

    ctx['nb'], ctx['js'] = export_notebook(nb, cid)
    return render(request, "mpcontribs_portal_contribution.html", ctx.flatten())


def cif(request, sid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    cif = client.structures.get_entry(pk=sid, _fields=['cif']).response().result['cif']
    if cif:
        return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)


def download_json(request, cid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contrib = client.contributions.get_entry(pk=cid, fields=['_all']).response().result
    if contrib:
        jcontrib = json.dumps(contrib)
        response = HttpResponse(jcontrib, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename={}.json'.format(cid)
        return response
    return HttpResponse(status=404)

def csv(request, project):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contribs = client.contributions.get_entries(
        project=project, _fields=['identifier', 'id', 'data']
    ).response().result['data']  # first 20 only

    data = []
    for contrib in contribs:
        data.append({})
        for k, v in nested_to_record(contrib, sep='.').items():
            if v is not None and not k.endswith('.value') and not k.endswith('.unit'):
                vs = v.split(' ')
                if k.endswith('.display') and len(vs) > 1:
                    key = k.replace('data.', '').replace('.display', '') + f' [{vs[1]}]'
                    data[-1][key] = vs[0]
                else:
                    data[-1][k] = v

    df = DataFrame(data)
    response = HttpResponse(df.to_csv(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename={}.csv'.format(project)
    return response

def apply(request):
    ctx = RequestContext(request)
    return render(request, "mpcontribs_portal_apply.html", ctx.flatten())
