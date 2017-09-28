from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class BoltztrapRester(MPContribsRester):
    """Boltztrap-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.doi': '10.1038/sdata.2017.85'}
    provenance_keys = ['title', 'authors', 'journal', 'doi', 'remarks']

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'volume', 'formula']

        docs = self.query_contributions(projection={'_id': 1, 'mp_cat_id': 1, 'content': 1})
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
                mp_id, cid_url, contrib['volume'], contrib['pretty_formula']
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
