from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app, render_template, g
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from mpcontribs.api import get_resource_as_string
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline

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
                description: dict with `cid` keys and structure names as values
                schema:
                    type: string
        """
        portal = 'http://localhost:8080' if current_app.config['DEBUG'] else 'https://portal.mpcontribs.org'
        mask = ['content.data', 'content.structures', 'identifier']
        search = request.args.get('q')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page

        objects = Contributions.objects.only(*mask)
        objects = objects(project=project)
        if search is not None:
            objects = objects(content__data__Formula__contains=search)

        columns = ['mp-id', 'contribution', 'formula', 'phase']
        columns += ['ΔH', 'ΔH|hyd', 'GS?', 'CIF']

        order = request.args.get('order')
        order_sign = '-' if order == 'desc' else '+'
        sort_by = request.args.get('sort_by')
        sort_by_key = sort_by if sort_by in columns else columns[0]
        order_by = f"{order_sign}{sort_by_key}"
        print(order_by)
        objects = objects.order_by(order_by)
        docs = objects.paginate(page=page, per_page=per_page).items

        pipeline = [
            {"$project": {"arrayofkeyvalue": {"$objectToArray": "$content.structures"}}},
            {"$project": {"keys": "$arrayofkeyvalue.k"}}
        ]
        cursor = objects.aggregate(*pipeline)
        struc_names = dict((str(doc["_id"]), doc["keys"]) for doc in cursor)

        items = []
        for doc in docs:
            mp_id = doc['identifier']
            contrib = doc['content']['data']
            formula = contrib['Formula'].replace(' ', '')
            row = [mp_id, f"{portal}/explorer/{doc['id']}", formula, contrib['Phase']]
            row += [contrib['ΔH'], contrib['ΔH|hyd'], contrib['GS']]
            cif_url = ''
            struc_name = struc_names.get(str(doc['id']), [None])[0] # TODO multiple structures
            if struc_name is not None:
                cif_url = f"{request.host_url}contributions/{doc['id']}/cif/{struc_name}"
            row.append(cif_url)
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

# url_prefix added in register_blueprint
multi_view = ContributionsView.as_view(ContributionsView.__name__)
contributions.add_url_rule('/', view_func=multi_view, methods=['GET'])#, 'POST'])

single_view = ContributionView.as_view(ContributionView.__name__)
contributions.add_url_rule('/<string:cid>', view_func=single_view,
                         methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])

card_view = CardView.as_view(CardView.__name__)
contributions.add_url_rule('/<string:cid>/card', view_func=card_view, methods=['GET'])

table_view = TableView.as_view(TableView.__name__)
contributions.add_url_rule('/<string:project>/table', view_func=table_view, methods=['GET'])

graph_view = GraphView.as_view(GraphView.__name__)
contributions.add_url_rule('/<string:project>/graph', view_func=graph_view, methods=['GET'])
