import os
import flask_mongorest
from dict_deep import deep_get
from mongoengine.queryset.visitor import Q
from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update
from pandas.io.json._normalize import nested_to_record
from mpcontribs.api import construct_query
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.document import Structures

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
projects = Blueprint("projects", __name__, template_folder=templates)


class ProjectsResource(Resource):
    document = Projects
    filters = {
        'title': [ops.IContains],
        'description': [ops.IContains],
        'authors': [ops.IContains]
    }
    fields = ['project', 'is_public', 'title']
    allowed_ordering = ['project', 'title', 'is_public']
    paginate = False

    @staticmethod
    def get_optional_fields():
        return ['authors', 'description', 'urls', 'other', 'columns']

    def value_for_field(self, obj, field):
        # add columns key to response if requested
        if field == 'columns':
            columns = []
            objects = list(Contributions.objects.aggregate(*[
                {"$match": {"project": obj.id}},
                {"$project": {"akv": {"$objectToArray": "$data"}}},
                {"$unwind": "$akv"},
                {"$project": {"root": "$akv.k", "level2": {
                    "$switch": {"branches": [{
                        "case": {"$eq": [{"$type": "$akv.v"}, "object"]},
                        "then": {"$objectToArray": "$akv.v"}
                    }], "default": [{}]}
                }}},
                {"$unwind": "$level2"},
                {"$project": {"column": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": ["$level2", {}]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "display"]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "value"]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "unit"]}, "then": "$root"},
                        ],
                        "default": {"$concat": ["$root", ".", "$level2.k"]}
                    }
                }}},
                {"$group": {"_id": None, "columns": {"$addToSet": "$column"}}}
            ]))
            if objects:
                columns += objects[0]['columns']

            projects = sorted(obj.id.split('_'))
            names = Structures.objects(project=obj.id).distinct("name")
            if names:
                if len(projects) == len(names):
                    for p, n in zip(projects, sorted(names)):
                        if p == n.lower():
                            columns.append(f'{n}.CIF')
                else:
                    columns.append('CIF')

            return sorted(columns)
        else:
            raise UnknownFieldError


class ProjectsView(SwaggerView):
    resource = ProjectsResource
    methods = [List, Fetch, Create, Delete, Update]

    def has_add_permission(self, request, obj):
        # only admins can add new projects
        return 'admin' in self.get_groups(request)

    def has_delete_permission(self, request, obj):
        # only admins can delete projects
        return 'admin' in self.get_groups(request)


# ADDITIONAL VIEWS


class TableView(SwaggerView):
    resource = ProjectsResource

    def get(self, pk):
        """Retrieve a table of contributions for a project.
        ---
        operationId: get_table
        parameters:
            - name: pk
              in: path
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: project name/slug
            - name: columns
              in: query
              type: array
              items:
                  type: string
              description: comma-separated list of column names to tabulate
            - name: filters
              in: query
              type: array
              items:
                  type: string
              description: list of `column__operator:value` filters \
                      with `column` in dot notation and `operator` in mongoengine format \
                      (http://docs.mongoengine.org/guide/querying.html#query-operators). \
                      `column` needs to be a valid field in `data`.
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
              description: substring to search for in first non-id column
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
        # config and parameters
        portal = 'http://localhost:8080' if current_app.config['DEBUG'] \
            else 'https://portal.mpcontribs.org'
        mp_site = 'https://materialsproject.org/materials'
        mask = ['data', 'identifier']
        search = request.args.get('q')
        filters = request.args.get('filters', '').split(',')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        order = request.args.get('order')
        sort_by = request.args.get('sort_by', 'identifier')
        general_columns = ['identifier', 'id']
        user_columns = request.args.get('columns', '').split(',')
        objects = Contributions.objects(project=pk).only(*mask)

        # default user_columns
        sample = objects.first()['data']
        data_keys = sorted(list(
            k.rsplit('.', 1)[0] if k.endswith('.display') else k
            for k, v in nested_to_record(sample, sep='.').items()
            if not k.endswith('.value') and not k.endswith('.unit')
        ))
        if not data_keys:
            return {
                'total_count': 0, 'total_pages': 0, 'page': 1,
                'last_page': 1, 'per_page': per_page, 'items': []
            }
        formula_key_exists = bool('formula' in data_keys)
        if formula_key_exists:
            general_columns.append('formula')
        else:
            # test whether search key exists in all docs and is not a number/object
            search_key = data_keys[0].replace('.', '__')
            q1 = {f'data__{search_key}__exists': False}
            q2 = {f'data__{search_key}__type': 'object'}
            if objects(Q(**q1) | Q(**q2)).count() < 1:
                general_columns.append(data_keys[0])
            else:
                general_columns.append('formula')

        if not user_columns[0]:
            if formula_key_exists:
                data_keys.remove('formula')
            user_columns = data_keys if 'formula' in general_columns else data_keys[1:]

        # add units to column names
        columns = general_columns.copy()
        for col in user_columns:
            if 'CIF' in col:
                columns.append(col)
                continue
            q_unit = {f'data__{col.replace(".", "__")}__exists': True}
            unit_sample = objects(**q_unit).only(f'data.{col}.unit').first()
            try:
                unit = deep_get(unit_sample, f'data.{col}.unit')
                columns.append(f'{col} [{unit}]')
            except KeyError:
                columns.append(col)

        # search and sort
        if search is not None:
            kwargs = {
                f'data__{general_columns[-1]}__exists': True,
                f'data__{general_columns[-1]}__contains': search
            }
            objects = objects(Q(identifier__contains=search) | Q(**kwargs))
        sort_by_key = sort_by
        if ' ' in sort_by and sort_by[-1] == ']':
            sort_by = sort_by.split(' ')[0]  # remove unit
            sort_by_key = f'data.{sort_by}.value'
        elif sort_by in columns[2:]:
            sort_by_key = f'data.{sort_by}'
        order_sign = '-' if order == 'desc' else '+'
        order_by = f"{order_sign}{sort_by_key}"
        objects = objects.order_by(order_by)

        if filters:
            query = construct_query(filters)
            objects = objects(**query)

        # generate table page
        items = []
        for doc in objects.paginate(page=page, per_page=per_page).items:
            mp_id = doc['identifier']
            contrib = nested_to_record(doc['data'], sep='.')
            search_value = contrib.get(general_columns[-1], mp_id).replace(' ', '')
            row = [f"{mp_site}/{mp_id}", f"{portal}/{doc['id']}", search_value]

            for idx, col in enumerate(user_columns):
                cell = ''
                if 'CIF' in col:
                    try:
                        if '.' in col:  # grouped columns
                            sname = '.'.join(col.split('.')[:-1])  # remove CIF string from field name
                            print(doc['id'], sname)
                            structure = Structures.objects.only('id').get(contribution=doc['id'], name=sname)
                        else:
                            structure = Structures.objects.only('id').filter(contribution=doc['id']).first()
                        cell = f"{portal}/{structure['id']}.cif"
                    except DoesNotExist:
                        pass
                else:
                    cell = contrib.get(col+'.value', contrib.get(col, ''))
                    if isinstance(cell, str) and cell.startswith('mp-'):
                        cell = f"{mp_site}/{cell}"
                row.append(str(cell))

            items.append(dict(zip(columns, row)))

        total_count = objects.count()
        total_pages = int(total_count/per_page)
        if total_pages % per_page:
            total_pages += 1

        return {
            'total_count': total_count, 'total_pages': total_pages, 'page': page,
            'last_page': total_pages, 'per_page': per_page, 'items': items
        }


table_view = TableView.as_view(TableView.__name__)
projects.add_url_rule('/<string:pk>/table', view_func=table_view, methods=['GET'])
