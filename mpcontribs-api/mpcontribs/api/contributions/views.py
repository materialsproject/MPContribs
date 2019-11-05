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

from mpcontribs.api import get_resource_as_string, construct_query
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions, Cards
from mpcontribs.api.contributions.redox_thermo_csp_views import isograph_view, energy_analysis_view

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
              maximum: 200
              description: number of results to return per page
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["project", "identifier"]
              description: comma-separated list of fields to return (MongoDB syntax)
            - name: filters
              in: query
              type: array
              items:
                  type: string
              description: list of `column__operator:value` filters \
                      with `column` in dot notation and `operator` in mongoengine format \
                      (http://docs.mongoengine.org/guide/querying.html#query-operators). \
                      `column` needs to be a valid field in `content.data`.
        responses:
            200:
                description: list of contributions
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ContributionsSchema'
        """
        mask = request.args.get('mask', 'project,identifier').split(',')
        projects = request.args.get('projects', '').split(',')
        identifiers = request.args.get('identifiers', '').split(',')
        contains = request.args.get('contains')
        filters = request.args.get('filters', '').split(',')

        page = int(request.args.get('page', 1))
        PER_PAGE_MAX = 200
        per_page = int(request.args.get('per_page', PER_PAGE_MAX))
        per_page = PER_PAGE_MAX if per_page > PER_PAGE_MAX else per_page

        objects = Contributions.objects.only(*mask)
        if projects and projects[0]:
            objects = objects(project__in=projects)
        if identifiers and identifiers[0]:
            objects = objects(identifier__in=identifiers)
        if contains:
            objects = objects(identifier__icontains=contains)
        if filters:
            query = construct_query(filters)
            objects = objects(**query)

        n = objects.count()
        page_max = int(n/per_page) + bool(n % per_page)
        if n < 1 or page > page_max:
            return []

        return [
            unflatten(dict(
                (k, v) for k, v in get_cleaned_data(self.marshal(entry)).items()
            ))
            for entry in objects.paginate(page=page, per_page=per_page).items
        ]


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


def get_cleaned_data(data):
    return dict(
        (k.rsplit('.', 1)[0] if k.endswith('.display') else k, v)
        for k, v in nested_to_record(data, sep='.').items()
        if not k.endswith('.value') and not k.endswith('.unit')
    )


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
        try:
            card = Cards.objects.get(id=cid)
        except DoesNotExist:
            ctx = {'cid': cid}
            mask = ['project', 'identifier', 'content.data']
            contrib = Contributions.objects.only(*mask).get(id=cid)
            info = Projects.objects.get(project=contrib.project)
            ctx['title'] = info.title
            ctx['descriptions'] = info.description.strip().split('.', 1)
            authors = [a.strip() for a in info.authors.split(',') if a]
            ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
            ctx['landing_page'] = f'/{contrib.project}/'
            ctx['more'] = f'/explorer/{cid}'
            ctx['urls'] = info.urls.values()
            card_script = get_resource_as_string('templates/linkify.min.js')
            card_script += get_resource_as_string('templates/linkify-element.min.js')
            card_script += get_resource_as_string('templates/card.min.js')
            data = unflatten(dict(
                (k, v) for k, v in get_cleaned_data(contrib.content.data).items()
                if not k.startswith('modal')
            ))
            browser = get_browser()
            browser.execute_script(card_script, data)
            bs = BeautifulSoup(browser.page_source, 'html.parser')
            ctx['data'] = bs.body.table
            browser.close()
            rendered = html_minify(render_template('card.html', **ctx))
            tree = html.fromstring(rendered)
            inline(tree)
            card = Cards(html=html.tostring(tree.body[0]).decode('utf-8'))
            card.id = cid  # to link to the according contribution
            card.save()

        del card.id
        return card.html


class ModalView(SwaggerView):

    def get(self, cid):
        """Retrieve modal data for a single contribution.
        ---
        operationId: get_modal_data
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
        responses:
            200:
                description: modal data as defined by contributor
                schema:
                    type: object
        """
        mask = ['project', 'identifier', 'content.data.modal']
        contrib = Contributions.objects.only(*mask).get(id=cid)
        data = contrib.content.data
        if 'modal' not in data:
            return {}
        return unflatten(get_cleaned_data(data))


# url_prefix added in register_blueprint
multi_view = ContributionsView.as_view(ContributionsView.__name__)
contributions.add_url_rule('/', view_func=multi_view, methods=['GET'])  # , 'POST'])

single_view = ContributionView.as_view(ContributionView.__name__)
contributions.add_url_rule('/<string:cid>', view_func=single_view, methods=['GET'])  # , 'PUT', 'PATCH', 'DELETE'])

card_view = CardView.as_view(CardView.__name__)
contributions.add_url_rule('/<string:cid>/card', view_func=card_view, methods=['GET'])

modal_view = ModalView.as_view(ModalView.__name__)
contributions.add_url_rule('/<string:cid>/modal', view_func=modal_view, methods=['GET'])

contributions.add_url_rule('/redox_thermo_csp_energy/',
                           view_func=energy_analysis_view, methods=['GET'])
contributions.add_url_rule('/<string:cid>/redox_thermo_csp/<string:plot_type>',
                           view_func=isograph_view, methods=['GET'])
