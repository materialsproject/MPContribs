import json
from Flask import make_response, current_app
from bson import json_util
from bson.objectid import ObjectId
from datetime import datetime, date

from app import api

# https://stackoverflow.com/a/11286887
# https://gist.github.com/akhenakh/2954605
class MongoJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        print(type(obj))
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, ObjectId):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

@api.representation('application/json')
def output_json(data, code, headers=None):
    settings = {'cls': MongoJsonEncoder}
    if current_app.debug:
        settings.setdefault('indent', 4)
    dumped = json.dumps(data, **settings) + "\n"
    resp = make_response(dumped, code)
    resp.headers.extend(headers or {})
    return resp

