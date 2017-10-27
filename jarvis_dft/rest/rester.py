# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class JarvisDftRester(MPContribsRester):
    """JarvisDft-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.doi': '10.1038/s41598-017-05402-0'}
    provenance_keys = ['title', 'description', 'authors', 'website', 'journal', 'doi', 'url']

    def get_contributions(self, typ):

        types = ['2d', '3d']
        if typ not in types:
            raise Exception('typ has to be 2d or 3d!')

        docs = self.query_contributions(
            criteria={'content.data.{}'.format(typ): {'$exists': 1}},
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for JarvisDft Explorer!')

        data = []
        columns = [
            'mp-id', 'cid', 'formula', 'final_energy', 'optB88vDW_bandgap',
            'mbj_bandgap', 'bulk_modulus', 'shear_modulus', 'jid'
        ]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            hdata = mpfile.hdata[mp_id]
            contrib = hdata['data'][typ]

            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [mp_id, cid_url] + [contrib[k] for k in columns[2:-1]]
            row.append(hdata['details_url'].format(contrib['jid']))
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
