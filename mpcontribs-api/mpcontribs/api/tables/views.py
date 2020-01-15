import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask_mongorest.exceptions import UnknownFieldError
from flask import Blueprint
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.projects.views import ProjectsResource
from mpcontribs.api.contributions.views import ContributionsResource

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
tables = Blueprint("tables", __name__, template_folder=templates)


class TablesResource(Resource):
    document = Tables
    related_resources = {'project': ProjectsResource, 'contribution': ContributionsResource}
    filters = {
        'id': [ops.In, ops.Exact],
        'contribution': [ops.In, ops.Exact],
        'is_public': [ops.Boolean],
        'name': [ops.In, ops.Exact, ops.Contains],
        'columns': [ops.IContains]
    }
    fields = ['id', 'contribution', 'is_public', 'name', 'columns']
    allowed_ordering = ['is_public', 'name']  # TODO data sorting
    paginate = True
    default_limit = 10
    max_limit = 20
    bulk_update_limit = 100
    fields_to_paginate = {'data': [20, 1000]}

    @staticmethod
    def get_optional_fields():
        return ['data', 'config', 'total_rows', 'total_pages']

    def value_for_field(self, obj, field):
        # add total_rows and total_pages keys for Backgrid
        table = Tables.objects.only('data').get(id=obj.id)
        total_rows = len(table.data)
        if field == 'total_rows':
            return total_rows
        elif field == 'total_pages':
            per_page = int(self.params.get('data_per_page', self.fields_to_paginate['data'][0]))
            return int(total_rows/per_page) + bool(total_rows % per_page)
        else:
            raise UnknownFieldError


class TablesView(SwaggerView):
    resource = TablesResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]

# REMOVE old graph view
# x, y, z = [], [], []
# if len(table.columns) > 2:
#     for col in table.columns[1:]:
#         x.append(col.split()[0])
#     for row in rows:
#         y.append(row[0])
#         z.append(row[1:])
# else:
#     for row in rows:
#         x.append(row[0])
#         y.append(row[1])
# return {'x': x, 'y': y, 'z': z} if z else {'x': x, 'y': y}
