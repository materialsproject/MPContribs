# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class BoltztrapRester(MPContribsRester):
    """Boltztrap-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.doi': '10.1038/sdata.2017.85'}
    provenance_keys = ['title', 'authors', 'journal', 'doi', 'url', 'remarks']

    def get_contributions(self, doping):

        dopings = ['n', 'p']
        if doping not in dopings:
            raise Exception('doping has to be n or p!')

        docs = self.query_contributions(projection={'_id': 1, 'mp_cat_id': 1, 'content': 1})
        if not docs:
            raise Exception('No contributions found for Boltztrap Explorer!')

        data = []
        columns = ['mp-id', 'cid', 'formula', u'mₑᶜᵒⁿᵈ', u"Sₘₐₓ", u"σₘₐₓ", u"κₑ₋ₘᵢₙ"]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']

            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            cond_eff_mass = contrib[columns[3]].get(doping, {}).get('<ε>', '')
            row = [mp_id, cid_url, contrib['pretty_formula'], cond_eff_mass]
            row += [contrib[k][doping]['value'] for k in columns[4:]]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
