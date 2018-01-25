from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class MpWorkshop2017Rester(MPContribsRester):
    """MpWorkshop2017-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))

    query = {'content.source': mpfile.hdata.general['source']}
    provenance_keys = [k for k in mpfile.hdata.general.keys() if k != 'google_sheet']

    def get_contributions(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content.data': 1}
        )
        if not docs:
            raise Exception('No contributions found for MpWorkshop2017 Explorer!')

        data = []
        columns = ['mp-id', 'contribution']

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']
            cid_url = self.get_cid_url(doc)

            for k in contrib.keys():
                if k not in columns:
                    columns.append(k)

            row = [mp_id, cid_url]
            for col in columns[2:]:
                row.append(contrib.get(col, ''))

            data.append([mp_id, row])

        # enforce equal row lengths
        ncols = len(columns)
        for entry in data:
            n = len(entry[1])
            if n != ncols:
                entry[1] += [''] * (ncols - n)

        return Table.from_items(data, orient='index', columns=columns)


    def get_graphs(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for MpWorkshop2017 Explorer!')

        graphs = {}
        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            graphs[mp_id] = mpfile.gdata[mp_id]

        return graphs
