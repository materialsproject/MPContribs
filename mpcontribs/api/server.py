import os

from flask import Flask, request
from flask_pymongo import PyMongo
from flask_restplus import Api

app = Flask(__name__)
app.secret_key = b'super-secret' # reset in local prod config
app.config['API_CHECK_ENDPOINT'] = 'https://materialsproject.org/rest/api_check'

credentials = os.environ.get('MPCONTRIBS_MONGO_USER_PASSWORD', '')
host = '{0}{1}{2}'.format(
    credentials, '@' if credentials else '',
    os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
)
app.config['MONGO_URI'] = "{0}://{1}/{2}?retryWrites=true".format(
    'mongodb+srv', host, 'mpcontribs'
)
mongo = PyMongo(app)


import re
from decorator import decorator
from requests import get
from flask import current_app
from flask_restplus.errors import abort
from flask_restplus._http import HTTPStatus

@decorator
def api_check(f, *args, **kw):
    # TODO SSL check?
    kwstr = ', '.join('%r: %r' % (k, kw[k]) for k in sorted(kw))
    print("calling %s with args %s, {%s}" % (f.__name__, args, kwstr))
    api_key = request.headers.get('X-API-KEY')
    if not api_key:
        abort(HTTPStatus.FORBIDDEN, "X-API-KEY not supplied.")
    if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
        abort(HTTPStatus.FORBIDDEN, "X-API-KEY wrong format.")
    api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
    if not api_check_endpoint:
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, 'API_CHECK_ENDPOINT not set!')
    headers = {'X-API-KEY': api_key}
    api_check_response = get(api_check_endpoint, headers=headers).json()
    if not api_check_response['api_key_valid']:
        abort(HTTPStatus.FORBIDDEN, "API_KEY is not a valid key.")
    return f(*args, **kw)


authorizations = {
    'apikey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-KEY'}
}
api = Api(
    app, ordered=True, version='1.0', title='MPContribs API',
    description='API for contributed Materials Project data',
    authorizations=authorizations, security='apikey', contact='phuck@lbl.gov',
    decorators = [api_check]
)


from flask_restplus import Namespace
from flask_restplus import Resource as OriginalResource
from flask_restplus.mask import Mask

class Resource(OriginalResource):
    """Resource with projection property for pymongo queries"""
    def projection(self, model):
        mask = Mask(request.headers.get('X-Fields', model.__mask__))
        return None if '*' in mask.keys() else mask



from models import model as contribution_model

namespace = Namespace(
    'contributions', description='operations for canonical contributions'
)
namespace.add_model(contribution_model.name, contribution_model)

@namespace.route('/')
class Contributions(Resource):

    # TODO pagination?
    @namespace.marshal_with(contribution_model, as_list=True)
    def get(self):
        return list(mongo.db.contributions.find(
            {"project": "dtu"}, self.projection(contribution_model)
        ).limit(2))

@namespace.route("/<ObjectId:cid>")
class Contribution(Resource):

    @namespace.marshal_with(contribution_model)
    def get(self, cid):
        return mongo.db.contributions.find_one(
            cid, self.projection(contribution_model)
        )

api.add_namespace(namespace)

if __name__ == '__main__':
    app.run(debug=True)
