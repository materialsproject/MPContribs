import os

from flask import Flask, request
from flask_pymongo import PyMongo
from flask_restplus import Api, Namespace, Resource
from flask_restplus.mask import Mask

from models import model

app = Flask(__name__)
app.secret_key = b'super-secret' # reset in local prod config

credentials = os.environ.get('MPCONTRIBS_MONGO_USER_PASSWORD', '')
host = '{0}{1}{2}'.format(
    credentials, '@' if credentials else '',
    os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
)
app.config['MONGO_URI'] = "{0}://{1}/{2}?retryWrites=true".format(
    'mongodb+srv', host, 'mpcontribs'
)
mongo = PyMongo(app)

authorizations = {
    'apikey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-KEY'}
}
api = Api(
    app, ordered=True, version='1.0', title='MPContribs API',
    description='API for contributed Materials Project data',
    authorizations=authorizations, security='apikey', contact='phuck@lbl.gov'
)

namespace = api.namespace(
    'contributions', description='operations for canonical contributions'
)
namespace.add_model(model.name, model)

@namespace.route('/')
class Contributions(Resource):

    # TODO pagination?
    @namespace.marshal_list_with(model)
    def get(self):
        return list(mongo.db.contributions.find(
            {"project": "dtu"}, model.__mask__
        ).limit(2))

@namespace.route("/<ObjectId:cid>")
class Contribution(Resource):

    # TODO api_key authorization (rest/api_check)
    # TODO apply projection on all views
    @namespace.marshal_with(model)
    def get(self, cid):
        mask = Mask(request.headers.get('X-Fields', model.__mask__))
        projection = None if '*' in mask.keys() else mask
        return mongo.db.contributions.find_one(cid, projection)

if __name__ == '__main__':
    app.run(debug=True)
