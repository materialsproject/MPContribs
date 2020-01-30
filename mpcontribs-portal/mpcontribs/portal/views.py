"""This module provides the views for the portal."""

import os
import json
import nbformat
from glob import glob
from time import sleep
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from fido.exceptions import HTTPTimeoutError

from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse
from django.urls import reverse
from django.template.loader import select_template

from mpcontribs.client import load_client
from mpcontribs.portal import get_consumer, get_context
from mpcontribs.io.core.components.hdata import HierarchicalData

def landingpage(request):
    ctx = RequestContext(request)
    project = request.path.replace('/', '')

    try:
        ctx.update(get_context(request, project))
    except Exception as ex:
        ctx['alert'] = str(ex)

    templates = [f'{project}_index.html', 'explorer_index.html']
    template = select_template(templates)
    return HttpResponse(template.render(ctx.flatten(), request))

def index(request):
    ctx = RequestContext(request)
    ctx['landing_pages'] = []
    mask = ['project', 'title', 'authors', 'is_public', 'description', 'urls']
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    entries = client.projects.get_entries(_fields=mask).result()['data']
    for entry in entries:
        authors = entry['authors'].strip().split(',', 1)
        if len(authors) > 1:
            authors[1] = authors[1].strip()
        entry['authors'] = authors
        entry['description'] = entry['description'].split('.', 1)[0] + '.'
        ctx['landing_pages'].append(entry)  # visibility governed by is_public flag and X-Consumer-Groups header
    return render(request, "home.html", ctx.flatten())


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
    nb = client.notebooks.get_entry(pk=cid).result()  # generate notebook with cells
    indexes = []
    for idx, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            last_line = cell['source'].rsplit('\n', 1)[-1]
            if not last_line.startswith('from') and ' = ' not in last_line:
                indexes.append(idx)
    ctx['indexes'] = json.dumps(indexes)

    if not nb['cells'][-1]['outputs']:
        try:
            nb = client.notebooks.get_entry(pk=cid).result(timeout=1)  # trigger cell execution
        except HTTPTimeoutError as e:
            dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>'
            ctx['alert'] = f'Detail page is building in the background {dots}'

    ctx['nb'], ctx['js'] = export_notebook(nb, cid)
    return render(request, "contribution.html", ctx.flatten())


def cif(request, sid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    cif = client.structures.get_entry(pk=sid, _fields=['cif']).result()['cif']
    if cif:
        return HttpResponse(cif, content_type='text/plain')
    return HttpResponse(status=404)


def download_json(request, cid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contrib = client.contributions.get_entry(pk=cid, fields=['_all']).result()
    if contrib:
        jcontrib = json.dumps(contrib)
        response = HttpResponse(jcontrib, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename={}.json'.format(cid)
        return response
    return HttpResponse(status=404)

def csv(request, project):
    from pandas import DataFrame
    from pandas.io.json._normalize import nested_to_record
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contribs = client.contributions.get_entries(
        project=project, _fields=['identifier', 'id', 'formula', 'data']
    ).result()['data']  # first 20 only

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

def notebooks(request, nb):
    return render(request, os.path.join('notebooks', nb + '.html'))

def healthcheck(request):
    return HttpResponse('OK')
