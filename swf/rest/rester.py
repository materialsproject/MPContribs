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
    query = {'content.doi': mpfile.hdata.general['doi']}

    def query_contributions(self, **kwargs):
        if 'criteria' in kwargs:
            kwargs['criteria'].update(self.query)
        else:
            kwargs['criteria'] = self.query
        return super(SWFRester, self).query_contributions(**kwargs)

    def delete_contributions(self, cids=[]):
        if not cids:
            cids = [c['_id'] for c in self.query_contributions()]
        return super(SWFRester, self).delete_contributions(cids)

    def get_contributions(self):
        docs = self.query_contributions(
            projection={'_id': 1, 'mp_cat_id': 1, 'content.data': 1}
        )
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        data = []
        columns = ['formula', 'contribution']

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            formula = mpfile.ids[0]
            contrib = mpfile.hdata[formula]['data']
            cid_url = self.get_cid_url(doc)

            for k in contrib.keys():
                if k not in columns:
                    columns.append(k)

            row = [formula, cid_url]
            for col in columns[2:]:
                row.append(contrib.get(col, ''))

            data.append([formula, row])

        # enforce equal row lengths
        ncols = len(columns)
        for entry in data:
            n = len(entry[1])
            if n != ncols:
                entry[1] += [''] * (ncols - n)

        return DataFrame.from_items(data, orient='index', columns=columns)


    def get_provenance(self):
        provenance_keys = ['title', 'doi', 'reference', 'authors', 'contributor', 'explanation']
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in provenance_keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(projection=projection)
        if not docs:
            raise Exception('No contributions found for SWF Explorer!')

        mpfile = MPFile.from_contribution(docs[0])
        formula = mpfile.ids[0]
        return mpfile.hdata[formula]

