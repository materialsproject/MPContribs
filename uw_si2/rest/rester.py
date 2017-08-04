from __future__ import division, unicode_literals
import six, bson, os
from bson.json_util import dumps, loads
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import get_short_object_id
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles
from pandas import Series

class UwSi2Rester(MPContribsRester):
    """UW/SI2-specific convenience functions to interact with MPContribs REST interface"""
    z = loads(open(os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'z.json'
    ), 'r').read())

    def get_uwsi2_contributions(self):
        data = []
        for doc in self.query_contributions(
            criteria={'content.figshare_id': '1546772'},
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        ):
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            table = mpfile.tdata[mp_id][mp_level01_titles[1]+'_D0_Q']
            anums = [self.z[el] for el in table['element']]
            table.insert(0, 'Z', Series(anums, index=table.index))
            table.sort_values('Z', inplace=True)
            table.reset_index(drop=True, inplace=True)
            hdata = mpfile.hdata[mp_id]
            data.append({
                'mp_id': mp_id, 'cid': doc['_id'],
                'short_cid': get_short_object_id(doc['_id']),
                'formula': hdata['formula'],
                'table': table
            })
        return data
