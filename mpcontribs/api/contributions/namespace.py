from flask_restplus import Namespace
from mpcontribs.api.core.resource_patched import Resource
from mpcontribs.api.core.decorators import api_check
from mpcontribs.api.contributions.models import contribution_model

contributions_namespace = Namespace(
    'contributions', decorators = [api_check],
    description='operations for canonical contributions',
)

@contributions_namespace.route('/')
class Contributions(Resource):

    @contributions_namespace.marshal_with(contribution_model, as_list=True)
    def get(self):
        return self.query()

@contributions_namespace.route('/<ObjectId:cid>')
class Contribution(Resource):

    @contributions_namespace.marshal_with(contribution_model)
    def get(self, cid):
        return self.query_one(cid)

contributions_namespace.add_model(contribution_model.name, contribution_model)

