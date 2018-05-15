# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components import Table
import os

class DefectGenomePcfcMaterialsRester(MPContribsRester):
    """defect_genome__pcfc_materials-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.urls.JPC': 'https://doi.org/10.1021/acs.jpcc.7b08716'}
    provenance_keys = ['title', 'description', 'authors', 'urls']
    released = True

    def get_contributions(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content.data': 1}
        )
        if not docs:
            raise Exception('No contributions found for PCFC Explorer!')

        data = []
        columns = ['mp-id', 'cid']
        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mpid = mpfile.ids[0]
            contrib = mpfile.hdata[mpid]['data']
            cid_url = self.get_cid_url(doc)
            row = [mpid, cid_url]
            if len(columns) == 2:
                columns += [k for k in contrib.keys()]
            for col in columns[2:]:
                row.append(contrib.get(col, ''))
            data.append((mpid, row))

        return Table.from_items(data, orient='index', columns=columns)


