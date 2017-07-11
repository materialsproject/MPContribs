from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class TamPerovskitesRester(MPContribsRester):
    """TamPerovskites-specific convenience functions to interact with MPContribs REST interface"""
    tam_perovskites_query = tuple({'content.emig': {'$exists': 1}}.iteritems())

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'efermi', 'ehull', 'bandgap']

        docs = self.query_contributions(
            criteria=self.tam_perovskites_query,
            projection={
                '_id': 1, 'mp_cat_id': 1,
                'content.efermi': 1, 'content.ehull': 1, 'content.bandgap': 1
            }
        )
        if not docs:
            raise Exception('No contributions found for TamPerovskites Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [
                mp_id, cid_url,
                contrib['efermi'], contrib['ehull'], contrib['bandgap']
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        provenance_keys = ['authors', 'abbreviations']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.tam_perovskites_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for DTU Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        mp_id = mpfile.ids[0]
        return mpfile.hdata[mp_id]

    def get_material(self, mpid):
        query = dict(self.tam_perovskites_query)
        query.update({'mp_cat_id': mpid})
        docs = self.query_contributions(criteria=query, projection={'content': 1})
        return docs[0] if docs else None
