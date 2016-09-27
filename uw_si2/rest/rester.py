from __future__ import division, unicode_literals
import six, bson, os
from bson.json_util import dumps, loads
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import get_short_object_id
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import Series

class UWSI2Rester(MPContribsRester):
    """UW/SI2-specific convenience functions to interact with MPContribs REST interface"""
    z = loads(open(os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'z.json'
    ), 'r').read())

    def get_uwsi2_contributions(self):
        """
        - [<host(pretty-formula)>] <mp_cat_id-linked-to-materials-details-page> <cid-linked-to-contribution-details-page>
            |- <solute> <D0-value> <Q-value> <toggle-in-graph>
            |- ...
        - ...
        """
        labels = ["Solute element name", "Solute D0 [cm^2/s]", "Solute Q [eV]"]
        data = []
        for doc in self.query_contributions(
            criteria={'project': {'$in': ['LBNL', 'UW-Madison']}},
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        ):
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            table = mpfile.tdata[mp_id]['data_supporting'][labels]
            table.columns = ['El.', 'D0 [cm2/s]', 'Q [eV]']
            anums = [self.z[el] for el in table['El.']]
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
