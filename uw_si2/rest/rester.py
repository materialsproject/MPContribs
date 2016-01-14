from __future__ import division, unicode_literals
import six, bson
from bson.json_util import dumps, loads
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import get_short_object_id

class UWSI2Rester(MPContribsRester):
    """UW/SI2-specific convenience functions to interact with MPContribs REST interface"""
    def get_uwsi2_contributions(self):
        """
        - [<host(pretty-formula)>] <mp_cat_id-linked-to-materials-details-page> <cid-linked-to-contribution-details-page>
            |- <solute> <D0-value> <Q-value> <toggle-in-graph>
            |- ...
        - ...
        """
        contribs = list(self.query_contributions(
            criteria={'project': 'LBNL'},
            projection={'mp_cat_id': 1}
        ))
        mp_ids = set(c['mp_cat_id'] for c in contribs)
        data = []
        for doc in self.query_contributions(
            criteria={'_id': {'$in': mp_ids}},
            projection=dict(
                ('.'.join(['LBNL', c['_id'], 'tables']), 1)
                for c in contribs
            ), collection='materials'
        ):
            for cid in doc['LBNL']:
                d = { 'mp_id': doc['_id'], 'cid': get_short_object_id(cid) }
                d['tables'] = doc['LBNL'][cid]['tables']
                data.append(d)
        return data
