import re
import os
import flask_mongorest
from flask import Blueprint
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask_mongorest.exceptions import UnknownFieldError
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.document import Structures
from mpcontribs.api.tables.document import Tables

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
contributions = Blueprint("contributions", __name__, template_folder=templates)
exclude = r'[^$.\s_~`^&(){}[\]\\;\'"/]'


class ContributionsResource(Resource):
    document = Contributions
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.Contains, ops.Exact],
        'is_public': [ops.Boolean],
        re.compile(r'^data__((?!__).)*$'): [ops.Contains, ops.Gte, ops.Lte]
    }
    fields = ['id', 'project', 'identifier', 'is_public']
    allowed_ordering = [
        'id', 'project', 'identifier', 'is_public',
        re.compile(r'^data(__(' + exclude + ')+){1,3}$')
    ]
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['data', 'structures', 'tables']

    def value_for_field(self, obj, field):
        # add structures and tables info to response if requested
        if field == 'structures':
            structures = Structures.objects.only('id', 'name').filter(contribution=obj.id)
            return [{'id': s.id, 'name': s.name} for s in structures]
        elif field == 'tables':
            tables = Tables.objects.only('id', 'name').filter(contribution=obj.id)
            return [{'id': t.id, 'name': t.name} for t in tables]
        else:
            raise UnknownFieldError

class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]
