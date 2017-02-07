from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import get_short_object_id
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

        for doc in self.query_contributions(
            criteria={
                'project': {'$in': ['LBNL', 'MIT']},
                'content.info.Phase': phase_query_key
            }, projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        ):
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            info = mpfile.hdata[mp_id]['info']
            row = [mp_id, get_short_object_id(doc['_id']), info['Formula']]
            if phase is None:
                row.append(info['Phase'])
            row += [info['dHf'], info['dHh'], info['GS'], 'TODO']
            # TODO URLs for mp_id and cid
            data.append((mp_id, row))

        return DataFrame.from_items(data, orient='index', columns=columns)

    def get_provenance(self):
        for doc in self.query_contributions(
            criteria={
                'project': {'$in': ['LBNL', 'MIT']}, 'content.Authors': {'$exists': 1},
                'content.Title': {'$exists': 1}, 'content.Reference': {'$exists': 1}
            },
            projection={
                '_id': 1, 'mp_cat_id': 1, 'content.Authors': 1,
                'content.Reference': 1, 'content.Title': 1
            }
        ):
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            return mpfile.hdata[mp_id]

    def get_phases(self):
        phases = set()

        for doc in self.query_contributions(
            criteria={
                'project': {'$in': ['LBNL', 'MIT']},
                'content.info.Phase': {'$exists': 1}
            }, projection={'_id': 0, 'content.info.Phase': 1}
        ):
            phases.add(doc['content']['info']['Phase'])

        return phases

