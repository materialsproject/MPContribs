import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Delete
from flask import Blueprint, current_app, render_template, g
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline
from mongoengine.queryset import DoesNotExist

from mpcontribs.api import get_resource_as_string, unflatten, get_cleaned_data
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.cards.document import Cards
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
cards = Blueprint("cards", __name__, template_folder=templates)


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


class CardsResource(Resource):
    document = Cards
    filters = {
        'project': [ops.In, ops.Exact],
        'is_public': [ops.Boolean]
    }
    fields = ['project', 'is_public', 'html']
    allowed_ordering = ['project']
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100


class CardsView(SwaggerView):
    resource = CardsResource
    methods = [List, Fetch, Delete]  # no create/update to disable arbitrary html content

    def get(self, **kwargs):
        cid = kwargs.get('pk')
        try:
            ret = super().get(**kwargs)
        except DoesNotExist:
            if cid:
                card = None
                try:
                    card = Cards.objects.only('id').get(id=cid)
                except DoesNotExist:  # Card has never been requested before
                    print('generating empty card ...')
                    # save an empty card
                    mask = ['project', 'identifier', 'is_public']
                    contrib = Contributions.objects.only(*mask).get(id=cid)
                    card = Cards(
                        id=cid,  # to link to the according contribution
                        is_public=contrib.is_public,  # in sync with contribution
                        project=contrib.project
                    )
                    card.save()
                    return self.get(**kwargs)

                if card is not None:
                    raise DoesNotExist(f'Card {card.id} exists but user not in project group')

            else:
                raise DoesNotExist('List Method')

        if not ret["html"]:
            # generate HTML content
            print('generating html...')
            ctx = {'cid': cid}
            card = Cards.objects.get(id=cid)
            info = Projects.objects.get(pk=card.project)
            ctx['title'] = info.title
            ctx['descriptions'] = info.description.strip().split('.', 1)
            authors = [a.strip() for a in info.authors.split(',') if a]
            ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
            ctx['landing_page'] = f'/{card.project}/'
            ctx['more'] = f'/{cid}'
            ctx['urls'] = info.urls.values()
            card_script = get_resource_as_string('templates/linkify.min.js')
            card_script += get_resource_as_string('templates/linkify-element.min.js')
            card_script += get_resource_as_string('templates/card.min.js')
            contrib = Contributions.objects.only('data').get(id=cid)
            data = unflatten(dict(
                (k, v) for k, v in get_cleaned_data(contrib.data).items()
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
            card.html = html.tostring(tree.body[0]).decode('utf-8')
            card.save()
            return self.get(**kwargs)

        return ret
