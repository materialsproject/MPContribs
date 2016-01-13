from __future__ import division, unicode_literals
import six, bson
from bson.json_util import dumps, loads
from mpcontribs.rest.rester import MPContribsRester

class UWSI2Rester(MPContribsRester):
    """UW/SI2-specific convenience functions to interact with MPContribs REST interface"""
    def get_uwsi2_contributions(self):
        """
        - [<host(pretty-formula)>] <mp_cat_id-linked-to-materials-details-page> <cid-linked-to-contribution-details-page>
            |- <solute> <D0-value> <Q-value> <toggle-in-graph>
            |- ...
        - ...
        """
        contribs = []
        for doc in self.query_contributions(
            criteria={'project': 'LBNL'},
            projection={'mp_cat_id': 1, 'content.data_supporting': 1}
        ):
            contrib = {
                'mp_id': doc['mp_cat_id'], 'cid': doc['_id'], 'solutes': []
            }
            d = doc['content']['data_supporting']
            for idx, solute in enumerate(d['solute element']):
                contrib['solutes'].append([
                    solute, d['D0 basal [cm^2/s]'][idx], d['Q basal [eV]'][idx]
                ])
            contribs.append(contrib)
        return contribs
