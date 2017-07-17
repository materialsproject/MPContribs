from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class SWFRester(MPContribsRester):
    """SWF-specific convenience functions to interact with MPContribs REST interface"""
    swf_query = tuple({
        'content.contributor': 'Sean W. Fackler',
        'content.compositions.Fe': {'$exists': 1},
        'content.compositions.Co': {'$exists': 1},
        'content.compositions.V': {'$exists': 1},
        'content.IP_Energy_product': {'$exists': 1},
        
    }.iteritems())

    def get_contributions(self):
        data = []
        columns = [
            'formula', 'contribution',
            'Fe', 'Co', 'V',
            'IP_Energy_product'
        ]

        docs = self.query_contributions(
            criteria=self.swf_query,
            projection={
                '_id': 1, 'mp_cat_id': 1,
                'content.compositions.Fe': 1,
                'content.compositions.Co': 1,
                'content.compositions.V': 1,
                'content.IP_Energy_product': 1}
        )
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            #changed
            formula = mpfile.ids[0]
            contrib = mpfile.hdata[formula]
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [
                formula, cid_url,
                contrib['compositions']['Fe'],
                contrib['compositions']['Co'],
                contrib['compositions']['V'],
                contrib['IP_Energy_product']
            ]
            data.append((formula, row))
        return DataFrame.from_items(data, orient='index', columns=columns)


    def get_provenance(self):
          
        provenance_keys = ['title', 'doi', 'reference', 'authors', 'contributor']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(criteria=self.swf_query, projection=projection)
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        #Changed below
        formula = mpfile.ids[0]
        return mpfile.hdata[formula]
    
    
       