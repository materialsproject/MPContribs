"""This module provides the views for the MnO2_phase_selection explorer interface."""

from django.shortcuts import render
from django.template import RequestContext
from test_site.settings import swagger_client as client
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.config import mp_level01_titles

#for doc in docs:
#    mpfile = MPFile.from_contribution(doc)
#    mp_id = mpfile.ids[0]
#    contrib = mpfile.hdata[mp_id]['data']
#    cid_url = self.get_cid_url(doc)
#    row = [mp_id, cid_url, contrib['Formula'].replace(' ', ''), contrib['Phase']]
#    row += [contrib['ΔH'], contrib['ΔH|hyd'], contrib['GS']]
#    cif_url = ''
#    structures = mpfile.sdata.get(mp_id)
#    if structures:
#        cif_url = '/'.join([
#            self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
#            doc['_id'], 'cif', structures.keys()[0]
#        ])
#    row.append(cif_url)
#    data.append((mp_id, row))

#return Table.from_items(data, orient='index', columns=columns)


def index(request):
    ctx = RequestContext(request)
    project = 'MnO2_phase_selection'
    try:
        # provenance
        prov = client.projects.get_entry(project=project).response().result
        prov.pop('id')
        ctx['title'] = prov.pop('title')
        ctx['provenance'] = RecursiveDict(prov).render()

        # overview table
        data = []
        columns = ['mp-id', 'contribution', 'formula', 'phase']
        columns += ['ΔH', 'ΔH|hyd', 'GS?', 'CIF']
        mask = ['identifier', 'content.data', f'content.{mp_level01_titles[3]}']
        #docs = client.contributions.get_entries(projects=[project], mask=mask).response().result
        ctx['table'] = 'world' #render_dataframe(df, webapp=True)
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "MnO2_phase_selection_explorer_index.html", ctx.flatten())
