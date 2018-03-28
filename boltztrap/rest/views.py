# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from webtzite import mapi_func
from webtzite.connector import ConnectorBase
from mpcontribs.rest.views import Connector
ConnectorBase.register(Connector)

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
def index(request, cid, db_type=None, mdb=None):
    try:
        response = 'hello'
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

