# -*- coding: utf-8 -*-
import re
import os
from collections import defaultdict
import flask_mongorest
from flask import Blueprint
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import *
from flask_mongorest.exceptions import UnknownFieldError
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.views import StructuresResource
from mpcontribs.api.tables.views import TablesResource

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
contributions = Blueprint("contributions", __name__, template_folder=templates)
exclude = r'[^$.\s_~`^&(){}[\]\\;\'"/]'


class ContributionsResource(Resource):
    document = Contributions
    related_resources = {"structures": StructuresResource, "tables": TablesResource}
    save_related_fields = ["structures", "tables"]
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
        re.compile(r"^data(__(" + exclude + ")+){1,3}$"),
    ]
    paginate = True
    default_limit = 20
    max_limit = 250
    download_formats = ["json", "csv"]

    @staticmethod
    def get_optional_fields():
        return ["data", "structures", "tables"]


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
