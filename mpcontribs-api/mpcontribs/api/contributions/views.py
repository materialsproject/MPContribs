import os
import flask_mongorest
from flask import Blueprint
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
contributions = Blueprint("contributions", __name__, template_folder=templates)


class ContributionsResource(Resource):
    document = Contributions
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.Contains, ops.Exact],
        'is_public': [ops.Boolean],
        'data__formula': [ops.Contains],
        'data__C__value': [ops.Gt]
        # query = construct_query(filters)  # TODO how to define filters on data?
    }
    fields = ['id', 'project', 'identifier', 'is_public']
    allowed_ordering = ['project', 'identifier', 'is_public']
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['data']


class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]

    # TODO unpack display from dict
    # https://github.com/tschaume/flask-mongorest/blob/9a04099daf9a93eefd6fd2ee906c29ffbb87789f/flask_mongorest/resources.py#L401
    # unflatten(dict(
    #     (k, v) for k, v in get_cleaned_data(<serialize_dict_field>).items()
    # ))
