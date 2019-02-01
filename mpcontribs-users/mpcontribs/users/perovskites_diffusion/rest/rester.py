from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class PerovskitesDiffusionRester(MPContribsRester):
    """PerovskitesDiffusion-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))
    query = {'content.doi': mpfile.hdata.general['doi']}
    provenance_keys = [k for k in mpfile.hdata.general.keys() if k != 'google_sheet']

    def get_contributions(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content.data': 1, 'content.abbreviations': 1}
        )
        if not docs:
            raise Exception('No contributions found for PerovskitesDiffusion Explorer!')

        data, columns = [], None
        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']
            cid_url = self.get_cid_url(doc)
            if columns is None:
                columns = ['mp-id', 'contribution'] + contrib.keys()
            row = [mp_id, cid_url] + contrib.values()
            data.append((mp_id, row))

        return Table.from_items(data, orient='index', columns=columns)

    def get_abbreviations(self):
        return self.get_global_hierarchical_data(['abbreviations']).get('abbreviations')
