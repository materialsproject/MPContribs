# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from webtzite import mapi_func
from webtzite.connector import ConnectorBase
from mpcontribs.rest.views import Connector
from mpcontribs.io.core.components import Table
ConnectorBase.register(Connector)

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
def index(request, cid, db_type=None, mdb=None):
    try:
        doc = mdb.contrib_ad.query_contributions(
            {'_id': cid}, projection={'_id': 0, 'content.S(p)': 1}
        )[0]
        table = Table.from_dict(doc['content']['S(p)'])
        x = [col.split()[0] for col in table.columns[1:]]
        y = list(table[table.columns[0]])
        z = table[table.columns[1:]].values.tolist()
        response = {'x': x, 'y': y, 'z': z, 'type': 'heatmap'}
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

