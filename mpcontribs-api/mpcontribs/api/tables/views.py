from flask import Blueprint, request, current_app
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables

tables = Blueprint("tables", __name__)

class TableView(SwaggerView):

    def get(self, tid):
        """Retrieve single table in DataFrame format.
        ---
        operationId: get_entry
        parameters:
            - name: tid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: Table ID (ObjectId)
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
            - name: mask
              in: query
              type: array
              items:
                  type: string
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: single table
                schema:
                    $ref: '#/definitions/TablesSchema'
        """
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        PER_PAGE_MAX = 200 # different for number of table rows
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        objects = Tables.objects.no_dereference()
        mask = request.args.get('mask')
        if mask:
            objects = objects.only(*mask.split(','))
        entry = objects.get(id=tid)
        entry.data = entry.paginate_field('data', page, per_page=per_page).items
        return self.marshal(entry)

class BackgridTableView(SwaggerView):

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
            - name: q
              in: query
              type: string
              description: substring to search for in formula
            - name: order
              in: query
              type: string
              description: sort ascending or descending
              enum: [asc, desc]
            - name: sort_by
              in: query
              type: string
              description: column name to sort by
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
        search = request.args.get('q')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        order = request.args.get('order')
        sort_by = request.args.get('sort_by')
        table = Tables.objects.get(cid=cid, name=name)
        #if search is not None: # TODO search first column?
        #    objects = objects(content__data__formula__contains=search)
        # TODO sorting
        items = [
            dict(zip(table.columns, row))
            for row in table.paginate_field('data', page, per_page=per_page).items
        ]
        total_count = len(table.data)
        total_pages = int(total_count/per_page)
        if total_pages%per_page:
            total_pages += 1
        return {
            'total_count': total_count, 'total_pages': total_pages, 'page': page,
            'last_page': total_pages, 'per_page': per_page, 'items': items
        }

single_view = TableView.as_view(TableView.__name__)
tables.add_url_rule('/<string:tid>', view_func=single_view,
                    methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])

table_view = BackgridTableView.as_view(BackgridTableView.__name__)
tables.add_url_rule('/<string:cid>/<string:name>', view_func=table_view, methods=['GET'])
