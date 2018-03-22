# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class DtuRester(MPContribsRester):
    """DTU-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.input_url': 'https://cmr.fysik.dtu.dk/_downloads/mp_gllbsc.db'}
    provenance_keys = ['title', 'input_url', 'description', 'urls', 'authors', 'contributor']
    released = True

    # TODO implement decorator to reduce this to column definitions and rows
    def get_contributions(self, bandgap_range=None):

        projection = {
            '_id': 1, 'mp_cat_id': 1,
            'content.formula': 1, 'content.ICSD': 1, 'content.data': 1
        }
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for DTU Explorer!')

        data = []
        columns = ['mp-id', 'cid', 'formula', 'ICSD', 'C']
        keys, subkeys = ['ΔE-KS', 'ΔE-QP'], ['indirect', 'direct']
        columns += ['##'.join([k, sk]) for k in keys for sk in subkeys]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = self.get_cid_url(doc)
            row = [mp_id, cid_url, contrib['formula'], contrib['ICSD'], contrib['data']['C']]
            row += [contrib['data'][k][sk] for k in keys for sk in subkeys]
            if bandgap_range:
                in_filter = True
                for k, v in bandgap_range.iteritems():
                    ks = k.split('_')
                    val = contrib['data'][ks[0]][ks[1]] if len(ks) > 1 else contrib['data'][k]
                    dec = float(val.split()[0])
                    if dec < v[0] or dec > v[1]:
                        in_filter = False
                        break
                if in_filter:
                    data.append((mp_id, row))
            else:
                data.append((mp_id, row))

        return Table.from_items(data, orient='index', columns=columns)
