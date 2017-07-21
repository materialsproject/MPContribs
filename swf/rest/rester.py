from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class SWFRester(MPContribsRester):
    """SWF-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))
    swf_query = tuple({'content.doi': mpfile.hdata.general['doi']}.iteritems())

    def get_contributions(self):
        data = []
        columns = [
            'formula', 'contribution',
            'Fe', 'Co', 'V',
            'IP_Energy_product','thickness','MOKE_IP_Hc','VSM_IP_Hc'
        ]

        docs = self.query_contributions(
            criteria=self.swf_query,
            projection={
                '_id': 1, 'mp_cat_id': 1,
                'content.Fe': 1,
                'content.Co': 1,
                'content.V': 1,
                'content.IP_Energy_product': 1,
                'content.thickness': 1,
                'content.MOKE_IP_Hc': 1,
                'content.VSM_IP_Hc': 1}
        )
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            formula = mpfile.ids[0]
            contrib = mpfile.hdata[formula]
            tables = mpfile.tdata.get(formula)
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'compositions', doc['_id']
            ])
            row = [
                formula, cid_url, tables,
                contrib['Fe'],
                contrib['Co'],
                contrib['V'],
                contrib['IP_Energy_product'],
                contrib['thickness'],
                contrib['MOKE_IP_Hc'],
                contrib['VSM_IP_Hc']
            ]
            data.append((formula, row))
        return DataFrame.from_items(data, orient='index', columns=columns)


    def get_provenance(self):
        provenance_keys = ['title', 'doi', 'reference', 'authors', 'contributor', 'explanation']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.swf_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        formula = mpfile.ids[0]
        return mpfile.hdata[formula]



