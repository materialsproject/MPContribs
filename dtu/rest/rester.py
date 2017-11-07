from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class DtuRester(MPContribsRester):
    """DTU-specific convenience functions to interact with MPContribs REST interface"""
    query = {
        'content.contributor': 'Technical University of Denmark',
        'content.kohn-sham_bandgap.indirect': {'$exists': 1},
        'content.kohn-sham_bandgap.direct': {'$exists': 1},
        'content.derivative_discontinuity': {'$exists': 1},
        'content.quasi-particle_bandgap.indirect': {'$exists': 1},
        'content.quasi-particle_bandgap.direct': {'$exists': 1},
    }
    provenance_keys = ['title', 'url', 'explanation', 'references', 'authors', 'contributor']
    released = True

    def get_contributions(self):
        projection = {'_id': 1, 'mp_cat_id': 1}
        projection.update(dict((k, 1) for k in self.query.keys()))
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for DTU Explorer!')

        data = []
        columns = [
            'mp-id', 'contribution',
            'kohn-sham_bandgap(indirect)', 'kohn-sham_bandgap(direct)',
            'derivative_discontinuity',
            'quasi-particle_bandgap(indirect)', 'quasi-particle_bandgap(direct)'
        ]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = self.get_cid_url(doc)
            row = [
                mp_id, cid_url,
                contrib['kohn-sham_bandgap']['indirect'],
                contrib['kohn-sham_bandgap']['direct'],
                contrib['derivative_discontinuity'],
                contrib['quasi-particle_bandgap']['indirect'],
                contrib['quasi-particle_bandgap']['direct']
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
