# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile

class SlacMose2Rester(MPContribsRester):
    """SLAC MoSe2-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.title': 'SLAC MoSe₂/2H-MoTe₂'}
    provenance_keys = ['title', 'authors', 'description', 'urls']
    released = True

    def get_contributions(self):

        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for SLAC MoSe2 Explorer!')

        import pandas as pd
        doc = docs[0] # there should be only one for MoSe2
        mpfile = MPFile.from_contribution(doc)
        mp_id = mpfile.ids[0]
        response = {}

        response['graphs'] = [
            plot for key, plot in mpfile.gdata[mp_id].items() if 'pump' in key
        ]

        tdata = mpfile.tdata[mp_id]
        name = tdata.keys()[-1]
        table = tdata[name]
        table = table.apply(pd.to_numeric)
        table.dropna(how='any', inplace=True)

        response['traces'] = []
        for col in table.columns[1:]:
            response['traces'].append({
                'x': table[table.columns[0]].values,
                'y': table[col].values,
                'name': col
            })

        return response
