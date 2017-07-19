from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class DibbsRester(MPContribsRester):
    """Dibbs-specific convenience functions to interact with MPContribs REST interface"""
    dibbs_query = tuple({'content.title': 'DIBBS - 27Al NMR'}.iteritems())

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'formula', 'CIF', 'dISO', 'etaQ', 'QCC', 'B']

        docs = self.query_contributions(
            criteria=self.dibbs_query,
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for Dibbs Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [mp_id, cid_url, contrib['formula']]
            cif_url = ''
            structures = mpfile.sdata.get(mp_id)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])
            row.append(cif_url)
            row += [contrib['data'][col] for col in columns[-4:]]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        provenance_keys = ['title']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.dibbs_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for Dibbs Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        mp_id = mpfile.ids[0]
        return mpfile.hdata[mp_id]

    def get_material(self, mpid):
        query = dict(self.dibbs_query)
        query.update({'mp_cat_id': mpid})
        docs = self.query_contributions(criteria=query, projection={'content': 1})
        return docs[0] if docs else None
