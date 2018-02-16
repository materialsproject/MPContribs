# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components import Table, Plot

class AlsBeamlineRester(MPContribsRester):
    """ALS Beamline-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.measurement_location': 'ALS Beamline 6.3.1'}
    provenance_keys = [
        'title', 'authors', 'description', 'measurement_location', 'method', 'sample'
    ]

    def get_contributions(self):
        projection = {'_id': 1, 'mp_cat_id': 1, 'content': 1}
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for ALS Beamline Explorer!')

        data = []
        columns = ['formula', 'cid']
        keys = RecursiveDict([
            ('composition', ['Co', 'Cu', 'Ce']),
            #('position', ['x', 'y']),
            ('XAS', ['min', 'max']),
            ('XMCD', ['min', 'max'])
        ])
        columns += ['##'.join([k, sk]) for k, subkeys in keys.items() for sk in subkeys]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            contrib = mpfile.hdata[identifier]['data']
            cid_url = self.get_cid_url(doc)
            row = [identifier, cid_url]
            row += [contrib[k][sk] for k, subkeys in keys.items() for sk in subkeys]
            data.append((identifier, row))
        return Table.from_items(data, orient='index', columns=columns)

    def get_all_spectra(self, typ):
        types = ['XAS', 'XMCD']
        if typ not in types:
            raise Exception('{} not in {}'.format(typ, types))

        projection = {'_id': 1, 'mp_cat_id': 1, 'content.Co': 1}
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for ALS Beamline Explorer!')

        table = Table()
        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            identifier = mpfile.ids[0]
            df = mpfile.tdata[identifier]['Co']
            if 'Energy' not in table.columns:
                table['Energy'] = df['Energy']
            table[identifier] = df[typ]

        return Plot({'x': 'Energy', 'table': typ, 'showlegend': False}, table)
