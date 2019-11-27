import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.tables.views import TablesResource

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
contributions = Blueprint("contributions", __name__, template_folder=templates)


class ContributionsResource(Resource):
    document = Contributions
    related_resources = {'tables': TablesResource}  # TODO structures
    save_related_fields = ['tables']  # TODO structures
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.IContains],
        'data__formula': [ops.Contains],
        'data__C__value': [ops.Gt]
        # query = construct_query(filters)  # TODO how to define filters on data?
        # TODO also enable filters on tables and structures?
    }
    fields = ['id', 'project', 'identifier']
    allowed_ordering = ['project', 'identifier']
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['data', 'structures', 'tables']


class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]
    # TODO unpack display from dict
    # https://github.com/tschaume/flask-mongorest/blob/9a04099daf9a93eefd6fd2ee906c29ffbb87789f/flask_mongorest/resources.py#L401
    # unflatten(dict(
    #     (k, v) for k, v in get_cleaned_data(<serialize_dict_field>).items()
    # ))
