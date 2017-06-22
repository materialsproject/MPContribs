from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class DtuRester(MPContribsRester):
    """DTU-specific convenience functions to interact with MPContribs REST interface"""
    dtu_query = {
        'content.contributor': 'Technical University of Denmark',
        'content.derivative_discontinuity': {'$exists': 1},
    }

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'derivative_discontinuity']

        docs = self.query_contributions(
            criteria=self.dtu_query,
            projection={'_id': 1, 'mp_cat_id': 1, 'content.derivative_discontinuity': 1}
        )
        if not docs:
            raise Exception('No contributions found for DTU Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            row = [mp_id, doc['_id'], contrib['derivative_discontinuity']]
            data.append((mp_id, row))

        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        provenance_keys = ['title', 'url', 'explanation', 'references', 'authors', 'contributor']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.dtu_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for DTU Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        mp_id = mpfile.ids[0]
        return mpfile.hdata[mp_id]
