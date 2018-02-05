from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile

class SlacMose2Rester(MPContribsRester):
    """SLAC MoSe2-specific convenience functions to interact with MPContribs REST interface"""
    query = {'project': {'$in': ['LBNL']}, 'content.formula': 'MoSe2'}
    provenance_keys = ['authors', 'description', 'reference']

    def get_graphs(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for SLAC MoSe2 Explorer!')

        doc = docs[0] # there should be only one for MoSe2
        mpfile = MPFile.from_contribution(doc)
        mp_id = mpfile.ids[0]
        graphs = mpfile.gdata[mp_id]

        return graphs
