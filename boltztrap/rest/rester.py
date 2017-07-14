from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class BoltztrapRester(MPContribsRester):
    """Boltztrap-specific convenience functions to interact with MPContribs REST interface"""
    boltztrap_query = tuple({
        'content.doi': '10.1038/sdata.2017.85',
        #'content.kohn-sham_bandgap.indirect': {'$exists': 1},
    }.iteritems())

    def get_contributions(self):
        data = []
        columns = [
            'mp-id', 'contribution',
        ]

        docs = self.query_contributions(
            criteria=self.boltztrap_query,
            projection={
                '_id': 1, 'mp_cat_id': 1,
            }
        )
        if not docs:
            raise Exception('No contributions found for Boltztrap Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [
                mp_id, cid_url,
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        provenance_keys = ['title', 'authors', 'journal', 'doi']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.boltztrap_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for Boltztrap Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        mp_id = mpfile.ids[0]
        return mpfile.hdata[mp_id]

    def get_material(self, mpid):
        query = dict(self.boltztrap_query)
        query.update({'mp_cat_id': mpid})
        docs = self.query_contributions(criteria=query, projection={'content': 1})
        return docs[0] if docs else None
