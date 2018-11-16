from flask_restplus import Namespace
from mpcontribs.api.resource import Resource
from mpcontribs.api.models import model as contribution_model
from mpcontribs.api.decorators import api_check

namespace = Namespace(
    'contributions', decorators = [api_check],
    description='operations for canonical contributions',
)

@namespace.route('/')
class Contributions(Resource):

    @namespace.marshal_with(contribution_model, as_list=True)
    def get(self):
        return self.query({'project': 'dtu'})

@namespace.route("/<ObjectId:cid>")
class Contribution(Resource):

    @namespace.marshal_with(contribution_model)
    def get(self, cid):
        return self.query_one(cid)

namespace.add_model(contribution_model.name, contribution_model)
