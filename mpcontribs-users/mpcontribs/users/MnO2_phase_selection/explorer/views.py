"""This module provides the views for the MnO2_phase_selection explorer interface."""

from django.shortcuts import render
from django.template import RequestContext
from test_site.settings import swagger_client as client
from test_site.settings import DEBUG
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components.tdata import Table

api_url = 'http://localhost:5000' if DEBUG else 'https://api.mpcontribs.org'

def index(request):
    ctx = RequestContext(request)
    project = 'MnO2_phase_selection'
    try:
        # provenance
        prov = client.projects.get_entry(project=project).response().result
        prov.pop('id')
        ctx['title'] = prov.pop('title')
        ctx['provenance'] = RecursiveDict(prov).render()
        host = request.build_absolute_uri()[:-1].rsplit('/', 1)[0]

        # overview table
        data = []
        columns = ['mp-id', 'contribution', 'formula', 'phase']
        columns += ['ΔH', 'ΔH|hyd', 'GS?', 'CIF']
        mask = ['identifier', 'content.data']
        docs = client.contributions.get_entries(projects=[project], mask=mask).response().result
        # TODO pagination (or do through Backgrid?)
        struc_names = client.contributions.get_structure_names(project=project).response().result

        for doc in docs:
            mp_id = doc['identifier']
            contrib = doc['content']['data']
            formula = contrib['Formula'].replace(' ', '')
            row = [mp_id, f"{host}/explorer/{doc['id']}", formula, contrib['Phase']]
            row += [contrib['ΔH'], contrib['ΔH|hyd'], contrib['GS']]
            cif_url = ''
            if struc_names.get(doc['id']):
                cif_url = f"{api_url}/contributions/{doc['id']}/cif/{struc_names[doc['id']][0]}"
            row.append(cif_url)
            data.append((mp_id, row))

        table = Table.from_items(data, orient='index', columns=columns)
        ctx['table'] = table.render()
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "MnO2_phase_selection_explorer_index.html", ctx.flatten())
