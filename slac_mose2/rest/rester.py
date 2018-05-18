# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile

class SlacMose2Rester(MPContribsRester):
    """SLAC MoSe2-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.title': 'SLAC MoSe₂/2H-MoTe₂'}
    provenance_keys = ['title', 'authors', 'description', 'urls']

    def get_graphs(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for SLAC MoSe2 Explorer!')

        doc = docs[0] # there should be only one for MoSe2
        mpfile = MPFile.from_contribution(doc)
        mp_id = mpfile.ids[0]
        graphs = mpfile.gdata[mp_id]

        return graphs

    def get_line_profiles(self):

        docs = self.query_contributions(
                projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
            )
        if not docs:
            raise Exception('No contributions found for SLAC MoSe2 Explorer!')

        doc = docs[0] # there should be only one for MoSe2
        mpfile = MPFile.from_contribution(doc)
        mp_id = mpfile.ids[0]
        table = mpfile.tdata[mp_id]['main_table']

        global_x_values = []
        y_values = {}

        for key, values in table.items():
            values = list(map(float, values))
            if 'delay time' in key:
                global_x_values = values
            else:
                y_values[key] = values

        return {
            'global_x_values': global_x_values,
            'y_values': y_values,
        }
