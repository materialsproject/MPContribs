from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class DibbsRester(MPContribsRester):
    """Dibbs-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.title': 'DIBBS - 27Al NMR'}
    provenance_keys = ['title']

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'formula', 'CIF', 'dISO', 'etaQ', 'QCC', 'B']

        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for Dibbs Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = self.get_cid_url(doc)
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
        return Table.from_items(data, orient='index', columns=columns)
