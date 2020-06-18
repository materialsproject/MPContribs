# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch
from flask import Blueprint, current_app, render_template, g, request
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from css_html_js_minify import html_minify
from lxml import html
from toronado import inline
from mongoengine.queryset import DoesNotExist
from fdict import fdict

from mpcontribs.api import get_resource_as_string, quantity_keys
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.cards.document import Cards
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
cards = Blueprint("cards", __name__, template_folder=templates)


def get_browser():
    if "browser" not in g:
        options = webdriver.ChromeOptions()
        options.add_argument("no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=800,600")
        options.add_argument("--disable-dev-shm-usage")
        options.set_headless()
        host = "chrome" if current_app.config["DEBUG"] else "127.0.0.1"
        g.browser = webdriver.Remote(
            command_executor=f"http://{host}:4444/wd/hub",
            desired_capabilities=DesiredCapabilities.CHROME,
            options=options,
        )
    return g.browser


class CardsResource(Resource):
    document = Cards
    filters = {"is_public": [ops.Boolean]}
    fields = ["is_public", "html"]


class CardsView(SwaggerView):
    resource = CardsResource
    # no create/update to disable arbitrary html content
    # card deletion via contributions
    methods = [Fetch]

    def get(self, **kwargs):
        cid = kwargs["pk"]  # only Fetch enabled
        qfilter = lambda qs: self.has_read_permission(request, qs.clone())
        try:
            # trigger DoesNotExist if necessary (due to permissions or non-existence)
            card = self._resource.get_object(cid, qfilter=qfilter)
            if not card.html:
                contrib = Contributions.objects.only("project", "data").get(pk=cid)
                info = Projects.objects.get(pk=contrib.project.id)
                ctx = {"cid": cid}
                ctx["title"] = info.title
                ctx["descriptions"] = info.description.strip().split(".", 1)
                authors = [a.strip() for a in info.authors.split(",") if a]
                ctx["authors"] = {"main": authors[0], "etal": authors[1:]}
                ctx["landing_page"] = f"/{contrib.project.id}/"
                ctx["more"] = f"/{cid}"
                ctx["urls"] = info.urls.values()
                card_script = get_resource_as_string("templates/linkify.min.js")
                card_script += get_resource_as_string(
                    "templates/linkify-element.min.js"
                )
                card_script += get_resource_as_string("templates/card.min.js")

                fd = fdict(contrib.data, delimiter=".")
                ends = [f".{qk}" for qk in quantity_keys]
                for key in list(fd.keys()):
                    if any(key.endswith(e) for e in ends):
                        value = fd.pop(key)
                        if key.endswith(ends[0]):
                            new_key = key.rsplit(".", 1)[0]  # drop .display
                            fd[new_key] = value
                data = fd.to_dict_nested()

                browser = get_browser()
                browser.execute_script(card_script, data)
                bs = BeautifulSoup(browser.page_source, "html.parser")
                ctx["data"] = bs.body.table
                # browser.close()
                rendered = html_minify(render_template("card.html", **ctx))
                tree = html.fromstring(rendered)
                inline(tree)
                card = Cards.objects.get(pk=cid)
                card.html = html.tostring(tree.body[0]).decode("utf-8")
                card.save()
            return self._resource.serialize(card, params=request.args)

        except DoesNotExist:
            card = None
            try:
                card = Cards.objects.only("pk").get(pk=cid)
            except DoesNotExist:  # Card has never been requested before
                # create and save unexecuted card, also start entry to avoid rebuild on subsequent requests
                contrib = Contributions.objects.only("project", "is_public").get(pk=cid)
                card = Cards(pk=cid, is_public=contrib.is_public)
                card.save()
                return self.get(**kwargs)

            if card is not None:
                raise DoesNotExist(
                    f"Card {card.pk} exists but user not in project group"
                )
