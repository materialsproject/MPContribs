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

    def get_contributions(self):

        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for JarvisDft Explorer!')

        data = []
        columns = ['mp-id', 'cid', 'formula']
        keys, subkeys = ['NUS', 'JARVIS'], ['id', 'Eₓ', 'CIF']
        columns += ['##'.join([k, sk]) for k in keys for sk in subkeys]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']
            cid_url = self.get_cid_url(doc)
            structures = mpfile.sdata.get(mp_id)

            row = [mp_id, cid_url, contrib['formula']]
            for k in keys:
                for sk in subkeys:
                    if sk == subkeys[-1]:
                        cif_url = ''
                        name = '{}_{}'.format(contrib['formula'], k)
                        if structures.get(name) is not None:
                            cif_url = '/'.join([
                                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                                doc['_id'], 'cif', name
                            ])
                        row.append(cif_url)
                    else:
                        cell = contrib.get(k, {sk: ''})[sk]
                        row.append(cell)

            if row[6]:
                data.append((mp_id, row))
        return Table.from_items(data, orient='index', columns=columns)
