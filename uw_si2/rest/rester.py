from __future__ import division, unicode_literals
import six, bson, os
from bson.json_util import dumps, loads
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import get_short_object_id

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
        labels = ["El.", "Z", "D0", "Q"]
        contribs = list(self.query_contributions(
            criteria={'project': 'LBNL'},
            projection={'mp_cat_id': 1}
        ))
        mp_ids, projection, data = set(), {}, []
        for c in contribs:
            mp_ids.add(c['mp_cat_id'])
            projection['.'.join(['LBNL', c['_id'], 'tables'])] = 1
            projection['.'.join(['LBNL', c['_id'], 'tree_data', 'formula'])] = 1
        for doc in self.query_contributions(
            criteria={'_id': {'$in': mp_ids}},
            projection=projection, collection='materials'
        ):
            for cid in doc['LBNL']:
                d = {
                    'mp_id': doc['_id'], 'cid': cid,
                    'short_cid': get_short_object_id(cid),
                    'formula': doc['LBNL'][cid]['tree_data']['formula']
                }
                d['tables'] = doc['LBNL'][cid]['tables']
                cols = d['tables']['data_supporting']['columns']
                for idx, col in enumerate(cols):
                    col['label'] = labels[idx]
                    col['editable'] = 'false'
                data.append(d)
        return data
