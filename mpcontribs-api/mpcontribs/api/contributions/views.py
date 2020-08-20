# -*- coding: utf-8 -*-
import re
import os
import flask_mongorest

from css_html_js_minify import html_minify
from json2html import Json2Html
from boltons.iterutils import remap

from flask import Blueprint, render_template
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import (
    Fetch,
    Delete,
    Update,
    BulkFetch,
    BulkCreate,
    BulkUpdate,
    BulkDelete,
    Download,
)
from flask_mongorest.exceptions import UnknownFieldError

from mpcontribs.api import enter, quantity_keys
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.views import StructuresResource
from mpcontribs.api.tables.views import TablesResource
from mpcontribs.api.notebooks.views import NotebooksResource

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
contributions = Blueprint("contributions", __name__, template_folder=templates)
exclude = r'[^$.\s_~`^&(){}[\]\\;\'"/]'
j2h = Json2Html()


def visit(path, key, value):
    if isinstance(value, dict) and quantity_keys == set(value.keys()):
        return key, value["display"]
    return True


class ContributionsResource(Resource):
    document = Contributions
    related_resources = {
        "structures": StructuresResource,
        "tables": TablesResource,
        "notebook": NotebooksResource,
    }
    save_related_fields = ["structures", "tables", "notebook"]
    filters = {
        "id": [ops.In, ops.Exact],
        "project": [ops.In, ops.Exact],
        "identifier": [ops.In, ops.Contains, ops.Exact],
        "formula": [ops.In, ops.Contains, ops.Exact],
        "is_public": [ops.Boolean],
        "last_modified": [ops.Gte, ops.Lte],
        re.compile(r"^data__((?!__).)*$"): [ops.Contains, ops.Gte, ops.Lte],
    }
    fields = ["id", "project", "identifier", "formula", "is_public", "last_modified"]
    allowed_ordering = [
        "id",
        "project",
        "identifier",
        "formula",
        "is_public",
        "last_modified",
        re.compile(r"^data(__(" + exclude + ")+){1,4}$"),
    ]
    paginate = True
    default_limit = 20
    max_limit = 250
    download_formats = ["json", "csv"]

    @staticmethod
    def get_optional_fields():
        return [
            "data",
            "structures",
            "tables",
            "notebook",
            "card_bootstrap",
            "card_bulma",
        ]

    def value_for_field(self, obj, field):
        if field.startswith("card_"):
            _, fmt = field.rsplit("_", 1)
            if fmt not in ["bootstrap", "bulma"]:
                raise UnknownFieldError

            if obj.project is None:
                obj.reload("id", "project", "data")

            project = obj.project.fetch()
            ctx = {
                "cid": str(obj.id),
                "title": project.title,
                "references": project.references[:5],
                "landing_page": f"/{project.id}/",
                "more": f"/{obj.id}",
            }
            ctx["descriptions"] = project.description.strip().split(".", 1)
            authors = [a.strip() for a in project.authors.split(",") if a]
            ctx["authors"] = {"main": authors[0], "etal": authors[1:]}
            ctx["data"] = j2h.convert(
                json=remap(obj.data, visit=visit, enter=enter),
                table_attributes='class="table is-narrow is-fullwidth has-background-light"',
            )
            return html_minify(render_template(f"card_{fmt}.html", **ctx))
        else:
            raise UnknownFieldError


class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [
        Fetch,
        Delete,
        Update,
        BulkFetch,
        BulkCreate,
        BulkUpdate,
        BulkDelete,
        Download,
    ]
