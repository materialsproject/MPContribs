# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import six, bson, os
from bson.json_util import loads
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.core.utils import clean_value
from mpcontribs.io.archieml.mpfile import MPFile

class DiluteSoluteDiffusionRester(MPContribsRester):
    """DiluteSoluteDiffusion-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.info.figshare_id': '1546772'}
    provenance_keys = ['title', 'authors', 'description', 'urls', 'info']
    z = loads(open(os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'z.json'
    ), 'r').read())

    def get_contributions(self, host):
        hosts = self.get_hosts()
        if host not in hosts:
            raise Exception('{} not a host: {}'.format(host, hosts))

        projection = {'_id': 1, 'mp_cat_id': 1, 'content._tdata_D₀_Q': 1}
        docs = self.query_contributions(
            criteria={'content.data.formula': host}, projection=projection
        )
        if not docs:
            raise Exception('No contributions found for DiluteSoluteDiffusion Explorer!')

        from pandas import Series
        mpfile = MPFile.from_contribution(docs[0])
        mp_id = mpfile.ids[0]
        table = mpfile.tdata[mp_id]['_tdata_D₀_Q']
        for col in table.columns:
            table[col] = table[col].apply(lambda x: clean_value(x))
        anums = [self.z[el] for el in table['El.']]
        table.insert(0, 'Z', Series(anums, index=table.index))
        table.sort_values('Z', inplace=True)
        table.reset_index(drop=True, inplace=True)
        return table

    def get_table_info(self, host):
        hosts = self.get_hosts()
        if host not in hosts:
            raise Exception('{} not a host: {}'.format(host, hosts))

        projection = {'_id': 1, 'mp_cat_id': 1}
        docs = self.query_contributions(
            criteria={'content.data.formula': host}, projection=projection
        )
        if not docs:
            raise Exception('No contributions found for DiluteSoluteDiffusion Explorer!')

        return {'cid': docs[0]['_id'], 'mp_id': docs[0]['mp_cat_id']}

    def get_hosts(self):
        hosts = set()
        docs = self.query_contributions(
            criteria={'content.data.formula': {'$exists': 1}},
            projection={'_id': 0, 'content.data.formula': 1}
        )
        if not docs:
            raise Exception('No contributions found for DiluteSoluteDiffusion Explorer!')

        for doc in docs:
            hosts.add(doc['content']['data']['formula'])

        return list(hosts)
