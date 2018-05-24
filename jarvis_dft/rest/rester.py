# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class JarvisDftRester(MPContribsRester):
    """JarvisDft-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))
    query = {'content.urls.DOI': mpfile.hdata.general['urls']['DOI']}
    provenance_keys = ['title', 'description', 'authors', 'urls']
    released = True

    def get_contributions(self):

        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for JarvisDft Explorer!')

        data, data_jarvis = [], []
        general_columns = ['mp-id', 'cid', 'formula']
        keys, subkeys = ['NUS', 'JARVIS'], ['id', 'Eₓ', 'CIF']
        columns = general_columns + ['##'.join([k, sk]) for k in keys for sk in subkeys]
        columns_jarvis = general_columns + ['id', 'E', 'ΔE|optB88vdW', 'ΔE|mbj', 'CIF']

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']
            cid_url = self.get_cid_url(doc)

            structures = mpfile.sdata.get(mp_id)
            cif_urls = {}
            for k in keys:
                cif_urls[k] = ''
                name = '{}_{}'.format(contrib['formula'], k)
                if structures.get(name) is not None:
                    cif_urls[k] = '/'.join([
                        self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                        doc['_id'], 'cif', name
                    ])

            row = [mp_id, cid_url, contrib['formula']]
            for k in keys:
                for sk in subkeys:
                    if sk == subkeys[-1]:
                        row.append(cif_urls[k])
                    else:
                        cell = contrib.get(k, {sk: ''})[sk]
                        row.append(cell)
            data.append((mp_id, row))

            row_jarvis = [mp_id, cid_url, contrib['formula']]
            for k in columns_jarvis[len(general_columns):]:
                if k == columns_jarvis[-1]:
                    row_jarvis.append(cif_urls[keys[1]])
                else:
                    row_jarvis.append(contrib.get(keys[1], {k: ''}).get(k, ''))
            if row_jarvis[3]:
                data_jarvis.append((mp_id, row_jarvis))

        return [
            Table.from_items(data, orient='index', columns=columns),
            Table.from_items(data_jarvis, orient='index', columns=columns_jarvis)
        ]
