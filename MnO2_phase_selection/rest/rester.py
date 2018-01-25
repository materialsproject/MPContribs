from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.components import Table

class Mno2PhaseSelectionRester(MPContribsRester):
    """MnO2_phase_selection-specific convenience functions to interact with MPContribs REST interface"""

    def get_contributions(self, phase=None):
        data = []
        phase_query_key = {'$exists': 1} if phase is None else phase
        columns = ['mp-id', 'contribution', 'formula']
        if phase is None:
            columns.append('phase')
        columns += ['dH (formation)', 'dH (hydration)', 'GS?', 'CIF']

        docs = self.query_contributions(
            criteria={
                'content.doi': '10.1021/jacs.6b11301',
                'content.data.Phase': phase_query_key
            },
            projection={
                '_id': 1, 'mp_cat_id': 1, 'content.data': 1,
                'content.{}'.format(mp_level01_titles[3]): 1
            }
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]['data']
            cid_url = self.get_cid_url(doc)
            row = [mp_id, cid_url, contrib['Formula']]
            if phase is None:
                row.append(contrib['Phase'])
            row += [contrib['dHf'], contrib['dHh'], contrib['GS']]
            cif_url = ''
            structures = mpfile.sdata.get(mp_id)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])
            row.append(cif_url)
            data.append((mp_id, row))

        return Table.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        docs = self.query_contributions(
            criteria={
                'content.doi': '10.1021/jacs.6b11301',
                'content.authors': {'$exists': 1},
                'content.title': {'$exists': 1},
                'content.reference': {'$exists': 1}
            },
            projection={
                '_id': 1, 'mp_cat_id': 1, 'content.authors': 1,
                'content.reference': 1, 'content.title': 1
            }
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            return mpfile.hdata[mp_id]

    def get_phases(self):
        phases = set()
        docs = self.query_contributions(
            criteria={
                'content.doi': '10.1021/jacs.6b11301',
                'content.data.Phase': {'$exists': 1}
            }, projection={'_id': 0, 'content.data.Phase': 1}
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            phases.add(doc['content']['data']['Phase'])

        return list(phases)

