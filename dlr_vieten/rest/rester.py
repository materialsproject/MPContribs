# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class DlrVietenRester(MPContribsRester):
    """DlrVieten-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.urls.GitHub': 'https://github.com/josuav1/solar_perovskite'}
    provenance_keys = ['title', 'authors', 'description', 'urls']

    def get_contributions(self):
        projection = {'_id': 1, 'mp_cat_id': 1, 'content': 1}
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for DlrVieten Explorer!')

        data, columns = [], ['identifier', 'contribution']

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            contrib = mpfile.hdata[identifier]['data']
            cid_url = self.get_cid_url(doc)
            row = [identifier, cid_url]

            scope = []
            for key, value in contrib.iterate():
                    level, key = key
                    level_reduction = bool(level < len(scope))
                    if level_reduction:
                        del scope[level:]
                    if value is None:
                        scope.append(key)
                    else:
                        col = '##'.join(scope + [key]).replace('_', ' ')
                        if col not in columns:
                            columns.append(col)
                        row.append(value)

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
