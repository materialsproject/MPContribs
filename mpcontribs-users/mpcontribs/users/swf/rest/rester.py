from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class SwfRester(MPContribsRester):
    """SWF-specific convenience functions to interact with MPContribs REST interface"""
    query = {'project': 'swf'}
    released = True

    def get_contributions(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'identifier': 1, 'content.data': 1}
        )
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        data = []
        columns = ['formula', 'contribution']
        ncols = 9

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            formula = mpfile.ids[0]
            contrib = mpfile.hdata[formula].get('data')
            if contrib is None:
                continue
            cid_url = self.get_cid_url(doc)

            for k in contrib.keys():
                if k not in columns:
                    columns.append(k)

            row = [formula, cid_url]
            for col in columns[2:]:
                row.append(contrib.get(col, ''))

            n = len(row)
            if n < ncols:
                row += [''] * (ncols - n)

            data.append((formula, row))

        return Table.from_items(data, orient='index', columns=columns)
