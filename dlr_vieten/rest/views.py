# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from webtzite import mapi_func

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def index(request, db_type=None, mdb=None):
    try:
        response = 'hello world'
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}
