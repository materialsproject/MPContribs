# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class BoltztrapRester(MPContribsRester):
    """Boltztrap-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.doi': '10.1038/sdata.2017.85'}
    provenance_keys = ['title', 'authors', 'journal', 'doi', 'url', 'remarks']

    def get_contributions(self):
        data = []
        columns = [
            'mp-id', 'contribution', 'formula', 'volume', u'<ε[n]>', u'<ε[p]>'
        ]

        docs = self.query_contributions(projection={'_id': 1, 'mp_cat_id': 1, 'content': 1})
        if not docs:
            raise Exception('No contributions found for Boltztrap Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']

            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [
                mp_id, cid_url, contrib['pretty_formula'], contrib['volume'],
                contrib['cond_eff_mass']['n']['<ε>'], contrib['cond_eff_mass']['p']['<ε>']
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
