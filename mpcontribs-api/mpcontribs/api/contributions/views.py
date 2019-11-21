import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
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
from mpcontribs.api.contributions.document import Contributions, Contents, Cards
from mpcontribs.api.contributions.redox_thermo_csp_views import isograph_view, energy_analysis_view

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
contributions = Blueprint("contributions", __name__, template_folder=templates)


class ContentsResource(Resource):
    document = Contents


class CardsResource(Resource):
    document = Cards


class ContributionsResource(Resource):
    document = Contributions
    related_resources = {'content': ContentsResource}
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.IContains],
        'content__data__C__value': [ops.Gt]
        #query = construct_query(filters) # TODO how to define filters on content?
    }
    fields = ['id', 'project', 'identifier']  # TODO return nested fields in content?
    allowed_ordering = ['project', 'identifier']
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['content']


class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]
    # TODO unpack display from dict
    # https://github.com/tschaume/flask-mongorest/blob/9a04099daf9a93eefd6fd2ee906c29ffbb87789f/flask_mongorest/resources.py#L401
    # unflatten(dict(
    #     (k, v) for k, v in get_cleaned_data(<serialize_dict_field>).items()
    # ))


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


card_view = CardView.as_view(CardView.__name__)
contributions.add_url_rule('/<string:cid>/card', view_func=card_view, methods=['GET'])

modal_view = ModalView.as_view(ModalView.__name__)
contributions.add_url_rule('/<string:cid>/modal', view_func=modal_view, methods=['GET'])

contributions.add_url_rule('/redox_thermo_csp_energy/',
                           view_func=energy_analysis_view, methods=['GET'])
contributions.add_url_rule('/<string:cid>/redox_thermo_csp/<string:plot_type>',
                           view_func=isograph_view, methods=['GET'])
