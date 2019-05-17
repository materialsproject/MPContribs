from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app, render_template, g
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from pandas.io.json.normalize import nested_to_record
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline
from typing import Any, Dict

from mpcontribs.api import get_resource_as_string
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions

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
        entry = Contributions.objects.get(id=cid).select_related()
        return self.marshal(entry)

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

# https://stackoverflow.com/a/55545369
def unflatten(
    d: Dict[str, Any],
    base: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Convert any keys containing dotted paths to nested dicts

    >>> unflatten({'a': 12, 'b': 13, 'c': 14})  # no expansion
    {'a': 12, 'b': 13, 'c': 14}

    >>> unflatten({'a.b.c': 12})  # dotted path expansion
    {'a': {'b': {'c': 12}}}

    >>> unflatten({'a.b.c': 12, 'a': {'b.d': 13}})  # merging
    {'a': {'b': {'c': 12, 'd': 13}}}

    >>> unflatten({'a.b': 12, 'a': {'b': 13}})  # insertion-order overwrites
    {'a': {'b': 13}}

    >>> unflatten({'a': {}})  # insertion-order overwrites
    {'a': {}}
    """
    if base is None:
        base = {}

    for key, value in d.items():
        root = base

        ###
        # If a dotted path is encountered, create nested dicts for all but
        # the last level, then change root to that last level, and key to
        # the final key in the path. This allows one final setitem at the bottom
        # of the loop.
        if '.' in key:
            *parts, key = key.split('.')

            for part in parts:
                root.setdefault(part, {})
                root = root[part]

        if isinstance(value, dict):
            value = unflatten(value, root.get(key, {}))

        root[key] = value

    return base

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
        card_script = get_resource_as_string('templates/linkify.min.js')
        card_script += get_resource_as_string('templates/linkify-element.min.js')
        card_script += get_resource_as_string('templates/card.min.js')
        data = unflatten(dict(
            (k.rsplit('.', 1)[0] if k.endswith('.display') else k, v)
            for k, v in nested_to_record(contrib.content.data, sep='.').items()
            if not k.endswith('.value') and not k.endswith('.unit')
        ))
        browser = get_browser()
        browser.execute_script(card_script, data)
        bs = BeautifulSoup(browser.page_source, 'html.parser')
        ctx['data'] = bs.body.table
        browser.close()
        rendered = html_minify(render_template('card.html', **ctx))
        tree = html.fromstring(rendered)
        inline(tree)
        card = html.tostring(tree.body[0]).decode('utf-8')
        return card


# url_prefix added in register_blueprint
multi_view = ContributionsView.as_view(ContributionsView.__name__)
contributions.add_url_rule('/', view_func=multi_view, methods=['GET'])#, 'POST'])

single_view = ContributionView.as_view(ContributionView.__name__)
contributions.add_url_rule('/<string:cid>', view_func=single_view,
                         methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])

card_view = CardView.as_view(CardView.__name__)
contributions.add_url_rule('/<string:cid>/card', view_func=card_view, methods=['GET'])
