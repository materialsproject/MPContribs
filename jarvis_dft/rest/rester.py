# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class JarvisDftRester(MPContribsRester):
    """JarvisDft-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))
    query = {'content.title': mpfile.hdata.general['title']}
    provenance_keys = ['title', 'description', 'authors', 'website', 'journal', 'doi', 'url']

    def get_contributions(self):

        docs = self.query_contributions(
            criteria={'content.data.2d_J': {'$exists': 1}, 'content.data.3d_J': {'$exists': 1}, 'content.data.2D': {'$exists': 1} },
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for JarvisDft Explorer!')

        data = []
        columns = ['mp-id', 'cid', 'CIF']
        keys, subkeys = ['2d_J', '3d_J', '2D'], ['exfoliation_energy', 'final_energy', 'source_detail_page']
        columns += ['##'.join([k, sk]) for k in keys for sk in subkeys]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            hdata = mpfile.hdata[mp_id]
            contrib = hdata['data']
            cid_url = self.get_cid_url(doc)
            cif_url = ''
            structures = mpfile.sdata.get(mp_id)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])

            row = [mp_id, cid_url, cif_url]
            for k in keys:
                for sk in subkeys:
                    if sk is subkeys[-1]:
                        if k is not '2D':
                            row.append(hdata['details_url_jarvis'].format(contrib[k]['source_detail_page']))
                        else:
                            row.append(hdata['details_url_2D'].format(contrib[k]['source_detail_page']))
                    else:
                        row.append(contrib[k][sk])
            data.append((mp_id, row))
        return Table.from_items(data, orient='index', columns=columns)
