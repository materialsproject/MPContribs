# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.components import Table

class Mno2PhaseSelectionRester(MPContribsRester):
    """MnO2_phase_selection-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.urls.JACS': 'https://doi.org/10.1021/jacs.6b11301'}
    provenance_keys = ['title', 'authors', 'description', 'urls']
    released = True

    def get_contributions(self, phase=None):
        data = []
        phase_query_key = {'$exists': 1} if phase is None else phase
        columns = ['mp-id', 'contribution', 'formula']
        if phase is None:
            columns.append('phase')
        columns += ['ΔH', 'ΔHₕ', 'GS?', 'CIF']

        docs = self.query_contributions(
            criteria={'content.data.Phase': phase_query_key},
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
            row = [mp_id, cid_url, contrib['Formula'].replace(' ', '')]
            if phase is None:
                row.append(contrib['Phase'])
            row += [contrib['ΔH'], contrib['ΔHₕ'], contrib['GS']]
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

    def get_phases(self):
        phases = set()
        docs = self.query_contributions(
            criteria={'content.data.Phase': {'$exists': 1}},
            projection={'_id': 0, 'content.data.Phase': 1}
        )
        if not docs:
            raise Exception('No contributions found for MnO2 Phase Selection Explorer!')

        for doc in docs:
            phases.add(doc['content']['data']['Phase'])

        return list(phases)
