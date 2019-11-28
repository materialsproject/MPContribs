import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask import Blueprint, request, current_app

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
tables = Blueprint("tables", __name__, template_folder=templates)


class TablesResource(Resource):
    document = Tables
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.Contains, ops.Exact],
        'name': [ops.Exact, ops.Contains],
        'cid': [ops.Exact],
        'is_public': [ops.Boolean]
    }
    fields = ['id', 'project', 'identifier', 'name', 'cid', 'is_public']
    allowed_ordering = ['project', 'identifier']
    paginate = True
    default_limit = 10
    max_limit = 20
    bulk_update_limit = 100
    fields_to_paginate = {'data': [20, 1000]}

    @staticmethod
    def get_optional_fields():
        return ['columns', 'data', 'config']


class TablesView(SwaggerView):
    resource = TablesResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]


class BackgridTableView(SwaggerView):
    resource = TablesResource

    def get(self, cid, name):
        """Retrieve a specific table for a contribution in backgrid format.
        ---
        operationId: get_table
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
            - name: name
              in: path
              type: string
              required: true
              description: table name
            - name: page
              in: query
              type: integer
              default: 1
              description: page to retrieve (in batches of `per_page`)
            - name: per_page
              in: query
              type: integer
              default: 20
              minimum: 2
              maximum: 20
              description: number of results to return per page
        responses:
            200:
                description: Paginated table response in backgrid format (items = rows of table)
                schema:
                    type: object
                    properties:
                        total_count:
                            type: integer
                        total_pages:
                            type: integer
                        page:
                            type: integer
                        last_page:
                            type: integer
                        per_page:
                            type: integer
                        items:
                            type: array
                            items:
                                type: object
        """
        # search = request.args.get('q')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        # order = request.args.get('order')
        # sort_by = request.args.get('sort_by')
        table = Tables.objects.get(cid=cid, name=name)
        # if search is not None: # TODO search first column?
        #     objects = objects(content__data__formula__contains=search)
        # TODO sorting
        items = [
            dict(zip(table.columns, row))
            for row in table.paginate_field('data', page, per_page=per_page).items
        ]
        total_count = len(table.data)
        total_pages = int(total_count/per_page)
        if total_pages % per_page:
            total_pages += 1
        return {
            'total_count': total_count, 'total_pages': total_pages, 'page': page,
            'last_page': total_pages, 'per_page': per_page, 'items': items
        }


class PlotlyTableView(SwaggerView):
    resource = TablesResource

    def get(self, project, identifier, name):
        """Retrieve a specific table for a contribution in Plotly format (x-y-z if #columns > 2).
        ---
        operationId: get_graph
        parameters:
            - name: project
              in: path
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: project name/slug
            - name: identifier
              in: path
              type: string
              required: true
              description: material/composition identifier
            - name: name
              in: path
              type: string
              required: true
              description: table name
            - name: page
              in: query
              type: integer
              default: 1
              description: page to retrieve (in batches of `per_page`)
            - name: per_page
              in: query
              type: integer
              default: 20
              minimum: 2
              maximum: 200
              description: number of results to return per page
        responses:
            200:
                description: Paginated table response in plotly format
                schema:
                    type: object
                    properties:
                        x:
                            type: array
                            items:
                                type: number
                        y:
                            type: array
                            items:
                                type: number
                        z:
                            type: array
                            items:
                                type: array
                                items:
                                    type: number
        """
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        PER_PAGE_MAX = 200  # different for number of table rows
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        table = Tables.objects.get(project=project, identifier=identifier, name=name)
        x, y, z = [], [], []
        rows = table.paginate_field('data', page, per_page=per_page).items
        if len(table.columns) > 2:
            for col in table.columns[1:]:
                x.append(col.split()[0])
            for row in rows:
                y.append(row[0])
                z.append(row[1:])
        else:
            for row in rows:
                x.append(row[0])
                y.append(row[1])

        return {'x': x, 'y': y, 'z': z} if z else {'x': x, 'y': y}


table_view = BackgridTableView.as_view(BackgridTableView.__name__)
tables.add_url_rule('/<string:cid>/<string:name>', view_func=table_view, methods=['GET'])

graph_view = PlotlyTableView.as_view(PlotlyTableView.__name__)
tables.add_url_rule('/<string:project>/<string:identifier>/<string:name>',
                    view_func=graph_view, methods=['GET'])
