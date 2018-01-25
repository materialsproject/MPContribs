# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_id_pattern
from mpcontribs.io.core.components import Table

class DlrVietenRester(MPContribsRester):
    """DlrVieten-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.author': 'Josua Vieten'}
    provenance_keys = ['title', 'author', 'description']

    def get_contributions(self):
        data = []
        columns = ['identifier', 'contribution', 'composition', 'CIF']

        docs = self.query_contributions(
            criteria={'content.title': {'$ne': 'Ionic Radii'}},
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for DlrVieten Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            contrib = mpfile.hdata[identifier]
            cid_url = self.get_cid_url(doc)
            row = [identifier, cid_url, contrib['composition']]
            cif_url = ''
            structures = mpfile.sdata.get(identifier)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])
            row.append(cif_url)
            data.append((identifier, row))
        return Table.from_items(data, orient='index', columns=columns)

    def get_ionic_radii(self):
        data = []
        columns = ['mp-id', 'cid', 'species', 'charge', u'rᵢₒₙ', 'HS/LS', 'CN']

        docs = self.query_contributions(
            criteria={'content.title': 'Ionic Radii'},
            projection={'_id': 1, 'mp_cat_id': 1, 'content.data': 1}
        )
        if not docs:
            raise Exception('No contributions found for DlrVieten Ionic Radii!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            contrib = mpfile.hdata[identifier]['data']
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            nrows = sum(1 for v in contrib.values() if isinstance(v, dict))
            rows = [[identifier, cid_url] for i in range(nrows)]

            for col in columns[2:]:
                for irow, row in enumerate(rows):
                    val = contrib.get(col)
                    if val is None:
                        val = contrib[str(irow)].get(col, '-')
                    row.append(val)

            for row in rows:
                data.append((identifier, row))

        return Table.from_items(data, orient='index', columns=columns)
