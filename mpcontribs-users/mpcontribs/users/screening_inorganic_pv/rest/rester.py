# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class ScreeninginorganicpvRester(MPContribsRester):
    """Screeninginorganicpv-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.project': 'Screeninginorganicpv'}
    provenance_keys = ['title', 'description', 'urls', 'authors']
    released = True

    # TODO implement decorator to reduce this to column definitions and rows
    def get_contributions(self):

        projection = {'_id': 1, 'mp_cat_id': 1, 'content.data': 1}
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for Screeninginorganicpv Explorer!')

        data = []
        columns = ['mp-id', 'cid', 'SLME|500nm', 'SLME|1000nm', 'mₑ', 'mₕ']
        keys, subkeys = ['ΔE'], ['corrected', 'direct', 'dipole-allowed']
        columns += ['##'.join([k, sk]) for k in keys for sk in subkeys]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = self.get_cid_url(doc)
            row = [mp_id, cid_url]
            row += [contrib['data'][k] for k in columns[2:-3]]
            row += [contrib['data'][k][sk] for k in keys for sk in subkeys]
            data.append((mp_id, row))

        return Table.from_items(data, orient='index', columns=columns)
