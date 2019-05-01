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

contributions = Blueprint("contributions", __name__)

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
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
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

    def get(self, cid, name):
        """Retrieve a specific table for a contribution.
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
        # config and parameters
        mask = [f'content.tables.{name}']
        search = request.args.get('q')
        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = current_app.config['PER_PAGE_MAX']
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page
        order = request.args.get('order')
        sort_by = request.args.get('sort_by')

        # query, projection and search
        entry = Contributions.objects.only(*mask).get(id=cid)
        columns = entry.content.tables.get(name, {}).get('columns')
        if columns is None:
            raise ValueError(f'{name} not valid table name for {cid}')
        #if search is not None: # TODO search first column?
        #    objects = objects(content__data__formula__contains=search)
        # TODO sorting

        #field, items = f'content.tables.{name}.data', []
        #for row in entry.content.tables[name].paginate_field('data', page, per_page=per_page).items:
        #    items.append(dict(zip(columns, row)))
        #    print(items[-1])
        return 'HELLO'


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
contributions.add_url_rule('/<string:cid>/table/<string:name>', view_func=table_view, methods=['GET'])
