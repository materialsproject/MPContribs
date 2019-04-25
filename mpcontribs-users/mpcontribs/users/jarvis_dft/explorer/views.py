# -*- coding: utf-8 -*-
"""This module provides the views for the jarvis_dft explorer interface."""

import json, os
from bson import ObjectId
from django.shortcuts import render_to_response, redirect
try:
    from django.core.urlresolvers import reverse
except ImportError:
    from django.urls import reverse
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict


def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from webtzite.models import RegisteredUser
        user = RegisteredUser.objects.get(username=request.user.username)
        from ..rest.rester import JarvisDftRester
        with JarvisDftRester(user.api_key, endpoint=get_endpoint(request)) as mpr:
            try:
                prov = mpr.get_provenance()
                ctx['title'] = prov.pop('title')
                ctx['provenance'] = render_dict(prov, webapp=True)
                ctx['tables'] = [
                    render_dataframe(table, webapp=True)
                    for table in mpr.get_contributions()
                ]
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        return redirect('{}?next={}'.format(reverse('cas_ng_login'), request.path))
    return render_to_response("jarvis_dft_explorer_index.html", ctx)

    #    data, data_jarvis = [], []
    #    general_columns = ['mp-id', 'cid', 'formula']
    #    keys, subkeys = ['NUS', 'JARVIS'], ['id', 'Eₓ', 'CIF']
    #    columns = general_columns + ['##'.join([k, sk]) for k in keys for sk in subkeys]
    #    columns_jarvis = general_columns + ['id', 'E', 'ΔE|optB88vdW', 'ΔE|mbj', 'CIF']

    #    for doc in docs:
    #        mpfile = MPFile.from_contribution(doc)
    #        mp_id = mpfile.ids[0]
    #        contrib = mpfile.hdata[mp_id]['data']
    #        cid_url = self.get_cid_url(doc)

    #        structures = mpfile.sdata.get(mp_id)
    #        cif_urls = {}
    #        for k in keys:
    #            cif_urls[k] = ''
    #            name = '{}_{}'.format(contrib['formula'], k)
    #            if structures.get(name) is not None:
    #                cif_urls[k] = '/'.join([
    #                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
    #                    doc['_id'], 'cif', name
    #                ])

    #        row = [mp_id, cid_url, contrib['formula']]
    #        for k in keys:
    #            for sk in subkeys:
    #                if sk == subkeys[-1]:
    #                    row.append(cif_urls[k])
    #                else:
    #                    cell = contrib.get(k, {sk: ''})[sk]
    #                    row.append(cell)
    #        data.append((mp_id, row))

    #        row_jarvis = [mp_id, cid_url, contrib['formula']]
    #        for k in columns_jarvis[len(general_columns):]:
    #            if k == columns_jarvis[-1]:
    #                row_jarvis.append(cif_urls[keys[1]])
    #            else:
    #                row_jarvis.append(contrib.get(keys[1], {k: ''}).get(k, ''))
    #        if row_jarvis[3]:
    #            data_jarvis.append((mp_id, row_jarvis))

    #    return [
    #        Table.from_items(data, orient='index', columns=columns),
    #        Table.from_items(data_jarvis, orient='index', columns=columns_jarvis)
    #    ]
