from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app, render_template, g
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from mpcontribs.api import get_resource_as_string
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from pymatgen import Structure
from pymatgen.io.cif import CifWriter
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline
from more_itertools import padded

contributions = Blueprint("contributions", __name__)
PER_PAGE_MAX = 20

class ContributionsView(SwaggerView):
    # TODO http://docs.mongoengine.org/guide/querying.html#raw-queries

    def get(self):
        """Retrieve (and optionally filter) contributions.
        ---
        operationId: get_entries
        parameters:
            - name: projects
              in: query
              type: array
              items:
                  type: string
              description: comma-separated list of projects
            - name: identifiers
              in: query
              type: array
              items:
                  type: string
              description: comma-separated list of identifiers
            - name: contains
              in: query
              type: string
              minLength: 3
              description: substring to search for in identifiers
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
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["project", "identifier"]
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: list of contributions
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ContributionsSchema'
        """
        mask = request.args.get('mask', 'project,identifier').split(',')
        objects = Contributions.objects.only(*mask)
        projects = request.args.get('projects', '').split(',')
        if projects and projects[0]:
            objects = objects(project__in=projects)
        identifiers = request.args.get('identifiers', '').split(',')
        if identifiers and identifiers[0]:
            objects = objects(identifier__in=identifiers)
        contains = request.args.get('contains')
        if contains:
            objects = objects(identifier__icontains=contains)
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        entries = objects.paginate(page=page, per_page=per_page).items
        return self.marshal(entries)

class ContributionView(SwaggerView):

    def get(self, cid):
        """Retrieve single contribution.
        ---
        operationId: get_entry
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
        responses:
            200:
                description: single contribution
                schema:
                    $ref: '#/definitions/ContributionsSchema'
        """
        entry = Contributions.objects.get(id=cid)
        return entry
        #return self.marshal(entry) # TODO also define contents in document!?

def get_browser():
    if 'browser' not in g:
        options = webdriver.ChromeOptions()
        options.add_argument("no-sandbox")
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=800,600')
        options.add_argument('--disable-dev-shm-usage')
        options.set_headless()
        host = 'chrome' if current_app.config['DEBUG'] else '127.0.0.1'
        g.browser = webdriver.Remote(
            command_executor=f"http://{host}:4444/wd/hub",
            desired_capabilities=DesiredCapabilities.CHROME,
            options=options
        )
    return g.browser

class CardView(SwaggerView):

    def get(self, cid):
        """Retrieve card for a single contribution.
        ---
        operationId: get_card
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
        responses:
            200:
                description: contribution card
                schema:
                    type: string
        """
        ctx = {'cid': cid}
        mask = ['project', 'identifier', 'content.data']
        contrib = Contributions.objects.only(*mask).get(id=cid)
        info = Projects.objects.get(project=contrib.project)
        ctx['title'] = info.title
        ctx['descriptions'] = info.description.strip().split('.', 1)
        authors = [a.strip() for a in info.authors.split(',') if a]
        ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
        debug = current_app.config['DEBUG']
        ctx['landing_page'] = f'/{contrib.project}'
        ctx['more'] = f'/explorer/{cid}'
        ctx['urls'] = info.urls.values()
        card_script = get_resource_as_string('templates/card.min.js')
        data = contrib.content.data
        browser = get_browser()
        browser.execute_script(card_script, data)
        src = browser.page_source.encode("utf-8")
        browser.close()
        bs = BeautifulSoup(src, 'html.parser')
        ctx['data'] = bs.body.table
        rendered = html_minify(render_template('card.html', **ctx))
        tree = html.fromstring(rendered)
        inline(tree)
        return html.tostring(tree.body[0])

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
              required: true
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
                description: paginated table response in backgrid format
                schema:
                    type: string
        """
        # config and parameters
        explorer = 'http://localhost:8080/explorer' if current_app.config['DEBUG'] \
            else 'https://portal.mpcontribs.org/explorer'
        mp_site = 'https://materialsproject.org/materials'
        mask = ['content.data', 'content.structures', 'identifier']
        search = request.args.get('q')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        general_columns = ['mp-id', 'cid', 'formula']
        user_columns = request.args.get('columns', '').split(',')
        columns = general_columns + user_columns
        grouped_columns = [list(padded(col.split('##'), n=2)) for col in user_columns]

        # documents
        objects = Contributions.objects(project=project).only(*mask)
        if search is not None:
            objects = objects(content__data__formula__contains=search)

        order = request.args.get('order')
        order_sign = '-' if order == 'desc' else '+'
        sort_by = request.args.get('sort_by')
        sort_by_key = sort_by if sort_by in columns else columns[0]
        order_by = f"{order_sign}{sort_by_key}"
        objects = objects.order_by(order_by)
        docs = objects.paginate(page=page, per_page=per_page).items

        # structure names
        pipeline = [
            {"$project": {"arrayofkeyvalue": {"$objectToArray": "$content.structures"}}},
            {"$project": {"keys": "$arrayofkeyvalue.k"}}
        ]
        cursor = objects.aggregate(*pipeline)
        struc_names = dict((str(doc["_id"]), doc.get("keys", [])) for doc in cursor)

        # generate table page
        items = []
        for doc in docs:
            mp_id = doc['identifier']
            contrib = doc['content']['data']
            formula = contrib['formula'].replace(' ', '')
            row = [f"{mp_site}/{mp_id}", f"{explorer}/{doc['id']}", formula]
            for k, sk in grouped_columns:
                cell = contrib.get(k, {sk: ''}).get(sk, '') if sk is not None else contrib.get(k, '')
                row.append(cell)

            ##if 'CIF' in columns
            #cif_url = ''
            #struc_name = struc_names.get(str(doc['id']), [None])[0] # TODO multiple structures
            #if struc_name is not None:
            #    cif_url = f"{explorer}/{doc['id']}/{struc_name}.cif"
            ## cif_urls = {}
            ## for k in keys:
            ##     cif_urls[k] = ''
            ##     name = '{}_{}'.format(contrib['formula'], k)
            ##     if structures.get(name) is not None:
            ##         cif_urls[k] = '/'.join([
            ##             self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
            ##             doc['_id'], 'cif', name
            ##         ])
            #row.append(cif_url)

            items.append(dict(zip(columns, row)))

            # row_jarvis = [mp_id, cid_url, contrib['formula']]
            # for k in columns_jarvis[len(general_columns):]:
            #     if k == columns_jarvis[-1]:
            #         row_jarvis.append(cif_urls[keys[1]])
            #     else:
            #         row_jarvis.append(contrib.get(keys[1], {k: ''}).get(k, ''))
            # if row_jarvis[3]:
            #     data_jarvis.append((mp_id, row_jarvis))

        total_count = objects.count()
        total_pages = int(total_count/per_page)
        if total_pages%per_page:
            total_pages += 1

        #    return [
        #        Table.from_items(data, orient='index', columns=columns),
        #        Table.from_items(data_jarvis, orient='index', columns=columns_jarvis)
        #    ]
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
              description: comma-separated list of column names to plot
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
        objects = Contributions.objects(project=project).only(*mask)
        data = [{'x': [], 'y': []} for col in columns]
        for obj in objects:
            for idx, col in enumerate(columns):
                data[idx]['x'].append(obj.identifier)
                val = obj['content']['data'][col].split(' ')[0]
                data[idx]['y'].append(val)
        return data

class CifView(SwaggerView):

    def get(self, cid, name):
        """Retrieve structure for contribution in CIF format.
        ---
        operationId: get_cif
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
              description: name of structure
        responses:
            200:
                description: structure in CIF format
                schema:
                    type: string
        """
        mask = [f'content.structures.{name}']
        entry = Contributions.objects.only(*mask).get(id=cid)
        structure = Structure.from_dict(entry.content.structures.get(name))
        if structure:
            return CifWriter(structure, symprec=1e-10).__str__()
        return f"Structure with name {name} not found for {cid}!" # TODO raise 404?


# url_prefix added in register_blueprint
multi_view = ContributionsView.as_view(ContributionsView.__name__)
contributions.add_url_rule('/', view_func=multi_view, methods=['GET'])#, 'POST'])

single_view = ContributionView.as_view(ContributionView.__name__)
contributions.add_url_rule('/<string:cid>', view_func=single_view,
                         methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])

card_view = CardView.as_view(CardView.__name__)
contributions.add_url_rule('/<string:cid>/card', view_func=card_view, methods=['GET'])

cif_view = CifView.as_view(CifView.__name__)
contributions.add_url_rule('/<string:cid>/<string:name>.cif', view_func=cif_view, methods=['GET'])

table_view = TableView.as_view(TableView.__name__)
contributions.add_url_rule('/<string:project>/table', view_func=table_view, methods=['GET'])

graph_view = GraphView.as_view(GraphView.__name__)
contributions.add_url_rule('/<string:project>/graph', view_func=graph_view, methods=['GET'])
