# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch
from flask import Blueprint, render_template, request
from css_html_js_minify import html_minify
from mongoengine.queryset import DoesNotExist
from json2html import Json2Html
from boltons.iterutils import remap

from mpcontribs.api import quantity_keys, delimiter
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.cards.document import Cards
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
cards = Blueprint("cards", __name__, template_folder=templates)
j2h = Json2Html()


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return key not in ["value", "unit"]


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
                ctx = info.to_mongo()
                ctx["cid"] = cid
                ctx["descriptions"] = info.description.strip().split(".", 1)
                authors = [a.strip() for a in info.authors.split(",") if a]
                ctx["authors"] = {"main": authors[0], "etal": authors[1:]}
                ctx["landing_page"] = f"/{contrib.project.id}/"
                ctx["more"] = f"/{cid}"
                data = contrib.to_mongo().get("data", {})
                ctx["data"] = j2h.convert(
                    json=remap(data, visit=visit), table_attributes='class="table"'
                )
                # TODO make html a DictField with bootstrap/bulma/... keys
                # NOTE holding off until switch to new MP website for MP detail pages
                card.html = html_minify(
                    render_template("card.html", **ctx)
                )  # bootstrap
                # TODO card.html_bulma
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
