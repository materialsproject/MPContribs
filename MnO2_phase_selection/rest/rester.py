from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class MnO2PhaseSelectionRester(MPContribsRester):
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
                'project': {'$in': ['LBNL', 'MIT', 'University of Kentucky']},
                'content.Phase': phase_query_key
            }, projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contrib = mpfile.hdata[mp_id]
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [mp_id, cid_url, contrib['Formula']]
            if phase is None:
                row.append(contrib['Phase'])
            row += [contrib['dHf'], contrib['dHh'], contrib['GS'], 'TODO']
            # TODO URLs for mp_id and cid
            data.append((mp_id, row))

        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        docs = self.query_contributions(
            criteria={
                'project': {'$in': ['LBNL', 'MIT','University of Kentucky']},
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
                'project': {'$in': ['LBNL', 'MIT','University of Kentucky']},
                'content.Phase': {'$exists': 1}
            }, projection={'_id': 0, 'content.Phase': 1}
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            phases.add(doc['content']['Phase'])

        return list(phases)

