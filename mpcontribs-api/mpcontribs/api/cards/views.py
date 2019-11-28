import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest.methods import Fetch, Delete
from flask_mongorest.views import mimerender, render_json, render_html
from flask import Blueprint, current_app, render_template, g
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline

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


class CardsView(SwaggerView):
    resource = CardsResource
    methods = [Fetch, Delete]

    @mimerender(default='json', json=render_json, html=render_html)
    def dispatch_request(self, *args, **kwargs):
        # generate card on demand
        resp = self._dispatch_request(*args, **kwargs)
        if isinstance(resp, tuple) and resp[1] == '404 Not Found':
            cid = kwargs['pk']
            ctx = {'cid': cid}
            mask = ['project', 'identifier', 'is_public', 'data']
            contrib = Contributions.objects.only(*mask).get(id=cid)
            info = Projects.objects.get(pk=contrib.project)
            ctx['title'] = info.title
            ctx['descriptions'] = info.description.strip().split('.', 1)
            authors = [a.strip() for a in info.authors.split(',') if a]
            ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
            ctx['landing_page'] = f'/{contrib.project}/'
            ctx['more'] = f'/{cid}'
            ctx['urls'] = info.urls.values()
            card_script = get_resource_as_string('templates/linkify.min.js')
            card_script += get_resource_as_string('templates/linkify-element.min.js')
            card_script += get_resource_as_string('templates/card.min.js')
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
            card = Cards(
                id=cid,  # to link to the according contribution
                is_public=contrib.is_public,  # in sync with contribution
                project=contrib.project,
                html=html.tostring(tree.body[0]).decode('utf-8')
            )
            card.save()
            resp = self._dispatch_request(*args, **kwargs)
        return resp
