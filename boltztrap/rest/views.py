# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json, math
from webtzite import mapi_func
from webtzite.connector import ConnectorBase
from mpcontribs.rest.views import Connector
from mpcontribs.io.core.components import Table
ConnectorBase.register(Connector)

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def index(request, cid, db_type=None, mdb=None):
    try:
        response = None
        if request.method == 'POST':
            name = json.loads(request.body)['name']
            names = name.split('##')
            table_name = '{}({})'.format(names[0][1:-1], names[1][0])
            doc = mdb.contrib_ad.query_contributions(
                {'_id': cid}, projection={'_id': 0, 'content.{}'.format(table_name): 1}
            )[0]
            table = doc['content'].get(table_name)
            if table:
                table = Table.from_dict(table)
                x = [col.split()[0] for col in table.columns[1:]]
                y = list(table[table.columns[0]])
                z = table[table.columns[1:]].values.tolist()
                if not table_name.startswith('S'):
                    z = [[math.log10(float(c)) for c in r] for r in z]
                title = ' '.join([table_name, names[1].split()[-1]])
                response = {'x': x, 'y': y, 'z': z, 'type': 'heatmap', 'colorbar': {'title': title}}
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

