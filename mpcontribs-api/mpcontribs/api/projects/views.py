from mongoengine.queryset import DoesNotExist
from mongoengine.context_managers import no_dereference
from mongoengine.queryset.visitor import Q
from flask import Blueprint, request, current_app
from bson.decimal128 import Decimal128
from pandas.io.json.normalize import nested_to_record
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.document import Structures

projects = Blueprint("projects", __name__)

class ProjectsView(SwaggerView):

    def get(self):
        """Retrieve (and optionally filter) projects.
        ---
        operationId: get_entries
        parameters:
            - name: search
              in: query
              type: string
              description: string to search for in `title`, `description`, and \
                      `authors` using a MongoEngine/MongoDB text index. Provide \
                      a space-separated list to the search query parameter to \
                      search for multiple words. For more, see \
                      https://docs.mongodb.com/manual/text-search/.
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["project", "title"]
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: list of projects
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ProjectsSchema'
        """
        mask = request.args.get('mask', 'project,title').split(',')
        objects = Projects.objects.only(*mask)
        search = request.args.get('search')
        entries = objects.search_text(search) if search else objects.all()
        return self.marshal(entries)

    # TODO: only staff can start new project
    def post(self):
        """Create a new project.
        Only MP staff can submit a new/non-existing project (or use POST
        endpoints in general). The staff member's email address will be set as
        the first readWrite entry in the permissions dict.
        """
        return NotImplemented()


class ProjectView(SwaggerView):

    def get(self, project):
        """Retrieve provenance info for a single project.
        ---
        operationId: get_entry
        parameters:
            - name: project
              in: path
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: project name/slug
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["title", "authors", "description", "urls"]
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: single project
                schema:
                    $ref: '#/definitions/ProjectsSchema'
        """
        mask_default = ','.join(['title', 'authors', 'description', 'urls'])
        mask = request.args.get('mask', mask_default).split(',')
        objects = Projects.objects.only(*mask)
        return self.marshal(objects.get(project=project))

    # TODO: only emails with readWrite permissions can use methods below
    def put(self, project):
        """Replace a project's provenance entry"""
        # TODO id/project are read-only
        return NotImplemented()

    def patch(self, project):
        """Partially update a project's provenance entry"""
        return NotImplemented()
        schema = self.Schema(dump_only=('id', 'project')) # id/project read-only
        schema.opts.model_build_obj = False
        payload = schema.load(request.json, partial=True)
        if payload.errors:
            return payload.errors # TODO raise JsonError 400?
        # set fields defined in model
        if 'urls' in payload.data:
            urls = payload.data.pop('urls')
            payload.data.update(dict(
                ('urls__'+key, getattr(urls, key)) for key in urls
            ))
        # set dynamic fields for urls
        for key, url in request.json.get('urls', {}).items():
            payload.data['urls__'+key] = url
        return payload.data
        #Projects.objects(project=project).update(**payload.data)

    def delete(self, project):
        """Delete a project's provenance entry"""
        # TODO should also delete all contributions
        return NotImplemented()

class TableView(SwaggerView):

    def get(self, project):
        """Retrieve a table of contributions for a project.
        ---
        operationId: get_table
        parameters:
            - name: project
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
        explorer = 'http://localhost:8080/explorer' if current_app.config['DEBUG'] \
            else 'https://portal.mpcontribs.org/explorer'
        mp_site = 'https://materialsproject.org/materials'
        mask = ['content.data', 'content.structures', 'identifier']
        search = request.args.get('q')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        order = request.args.get('order')
        sort_by = request.args.get('sort_by', 'identifier')
        general_columns = ['identifier', 'id']
        user_columns = request.args.get('columns', '').split(',')
        objects = Contributions.objects(project=project).only(*mask)

        # default user_columns
        sample = objects.first()['content']['data']
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
            q1 = {f'content__data__{search_key}__exists': False}
            q2 = {f'content__data__{search_key}__type': 'object'}
            if objects(Q(**q1) | Q(**q2)).count() < 1:
                general_columns.append(data_keys[0])
            else:
                general_columns.append('formula')

        if not user_columns[0]:
            if formula_key_exists:
                data_keys.remove('formula')
            user_columns = data_keys if 'formula' in general_columns else data_keys[1:]

        # add units to column names
        units = [objects.distinct(f'content.data.{col}.unit') for col in user_columns]
        columns = general_columns + [
            '{} [{}]'.format(col, units[idx][0])
            if units[idx] else col
            for idx, col in enumerate(user_columns)
        ]

        # search and sort
        if search is not None:
            kwargs = {
                f'content__data__{general_columns[-1]}__exists': True,
                f'content__data__{general_columns[-1]}__contains': search
            }
            objects = objects(Q(identifier__contains=search) | Q(**kwargs))
        sort_by_key = sort_by
        if ' ' in sort_by and sort_by[-1] == ']':
            sort_by = sort_by.split(' ')[0] # remove unit
            sort_by_key = f'content.data.{sort_by}.value'
        elif sort_by in columns[2:]:
            sort_by_key = f'content.data.{sort_by}'
        order_sign = '-' if order == 'desc' else '+'
        order_by = f"{order_sign}{sort_by_key}"
        objects = objects.order_by(order_by)

        # generate table page
        items = []
        for doc in objects.paginate(page=page, per_page=per_page).items:
            mp_id = doc['identifier']
            contrib = nested_to_record(doc['content']['data'], sep='.')
            search_value = contrib.get(general_columns[-1], mp_id).replace(' ', '')
            row = [f"{mp_site}/{mp_id}", f"{explorer}/{doc['id']}", search_value]

            for idx, col in enumerate(user_columns):
                cell = ''
                if 'CIF' in col:
                    structures = doc['content']['structures']
                    if '.' in col: # grouped columns
                        sname = '.'.join(col.split('.')[:-1]) # remove CIF string from field name
                        for d in structures:
                            if d['name'] == sname:
                                cell = f"{explorer}/{d['id']}.cif"
                                break
                    elif structures:
                        cell = f"{explorer}/{structures[0]['id']}.cif"
                else:
                    cell = contrib.get(col+'.value', contrib.get(col, ''))
                row.append(str(cell))

            items.append(dict(zip(columns, row)))

        total_count = objects.count()
        total_pages = int(total_count/per_page)
        if total_pages%per_page:
            total_pages += 1

        return {
            'total_count': total_count, 'total_pages': total_pages, 'page': page,
            'last_page': total_pages, 'per_page': per_page, 'items': items
        }

class GraphView(SwaggerView):

    def get(self, project):
        """Retrieve overview graph for a project.
        ---
        operationId: get_graph
        parameters:
            - name: project
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
              required: true
              description: comma-separated list of column names to plot (in MongoDB dot notation)
            - name: filters
              in: query
              type: array
              items:
                  type: string
              description: list of `column__operator:value` filters \
                      with `column` in dot notation and `operator` in mongoengine format \
                      (http://docs.mongoengine.org/guide/querying.html#query-operators). \
                      `column` needs to be a valid field in `content.data`.
            - name: page
              in: query
              type: integer
              default: 1
              description: page to retrieve (in batches of `per_page`)
            - name: per_page
              in: query
              type: integer
              default: 200
              minimum: 2
              maximum: 200
              description: number of results to return per page
        responses:
            200:
                description: x-y-data in plotly format
                schema:
                    type: array
                    items:
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
        """
        mask = ['content.data', 'identifier']
        columns = request.args.get('columns').split(',')
        filters = request.args.get('filters', '').split(',')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = 200
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page

        with no_dereference(Contributions) as ContributionsDeref:
            query = {'project': project}
            query.update(dict((
                f'content__data__{col.replace(".", "__")}__display__exists', True
            ) for col in columns))
            objects = ContributionsDeref.objects(**query).only(*mask)

            if filters:
                # C__gte:0.42,C__lte:2.10,ΔE-QP.direct__lte:11.3
                # -> content__data__C__value__lte
                query = {}
                for f in filters:
                    if '__' in f and ':' in f:
                        k, v = f.split(':')
                        col, op = k.rsplit('__', 1)
                        col = col.replace(".", "__")
                        key = f'content__data__{col}__value__{op}'
                        query[key] = float(v)
                objects = objects(**query)

            data = [{'x': [], 'y': [], 'text': []} for col in columns]
            for obj in objects.paginate(page=page, per_page=per_page).items:
                d = nested_to_record(obj['content']['data'], sep='.')
                for idx, col in enumerate(columns):
                    val = d[f'{col}.display']
                    data[idx]['x'].append(obj.identifier)
                    data[idx]['y'].append(val.split(' ')[0])
                    data[idx]['text'].append(str(obj.id))
            return data

# url_prefix added in register_blueprint
# also see http://flask.pocoo.org/docs/1.0/views/#method-views-for-apis
multi_view = ProjectsView.as_view(ProjectsView.__name__)
projects.add_url_rule('/', view_func=multi_view, methods=['GET'])#, 'POST'])

single_view = ProjectView.as_view(ProjectView.__name__)
projects.add_url_rule('/<string:project>', view_func=single_view,
                         methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])

table_view = TableView.as_view(TableView.__name__)
projects.add_url_rule('/<string:project>/table', view_func=table_view, methods=['GET'])

graph_view = GraphView.as_view(GraphView.__name__)
projects.add_url_rule('/<string:project>/graph', view_func=graph_view, methods=['GET'])
