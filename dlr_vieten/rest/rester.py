from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_id_pattern
from pandas import DataFrame

class DlrVietenRester(MPContribsRester):
    """DlrVieten-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.author': 'Josua Vieten'}
    provenance_keys = ['title', 'author', 'description', 't']

    def get_contributions(self):
        data = []
        columns = ['identifier', 'contribution', 'composition', 'CIF']

        docs = self.query_contributions(projection={'_id': 1, 'mp_cat_id': 1, 'content': 1})
        if not docs:
            raise Exception('No contributions found for DlrVieten Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            contrib = mpfile.hdata[identifier]
            endpoint = 'materials' if mp_id_pattern.match(identifier) else 'compositions'
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', endpoint, doc['_id']
            ])
            row = [identifier, cid_url, contrib['composition']]
            cif_url = ''
            structures = mpfile.sdata.get(identifier)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])
            row.append(cif_url)
            data.append((identifier, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
