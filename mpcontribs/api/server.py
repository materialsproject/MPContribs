import os

from flask import Flask
from flask_pymongo import PyMongo
from flask_restplus import Api
from mpcontribs.api.decorators import api_check

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

authorizations = {
    'apikey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-KEY'}
}
api = Api(
    app, ordered=True, version='1.0', title='MPContribs API',
    description='API for contributed Materials Project data',
    authorizations=authorizations, security='apikey', contact='phuck@lbl.gov',
    decorators = [api_check]
)


from flask import request
from flask_restplus import Namespace
from flask_restplus import Resource as OriginalResource
from flask_restplus.mask import Mask

class Resource(OriginalResource):
    """Resource with projection property for pymongo queries"""
    def projection(self, model):
        mask = Mask(request.headers.get('X-Fields', model.__mask__))
        return None if '*' in mask.keys() else mask



from mpcontribs.api.models import model as contribution_model

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
