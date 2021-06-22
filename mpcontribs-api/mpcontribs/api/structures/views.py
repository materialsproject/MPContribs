# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch, Download
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
structures = Blueprint("structures", __name__, template_folder=templates)


class StructuresResource(Resource):
    document = Structures
    filters = {
        "id": [ops.In, ops.Exact],
        "name": [ops.In, ops.Exact, ops.Contains],
        "md5": [ops.In, ops.Exact],
    }
    fields = ["id", "name", "md5"]
    allowed_ordering = ["name"]
    paginate = True
    default_limit = 10
    max_limit = 100
    download_formats = ["json", "csv"]

    @staticmethod
    def get_optional_fields():
        return ["lattice", "sites", "charge", "cif"]


class StructuresView(SwaggerView):
    resource = StructuresResource
    methods = [Fetch, BulkFetch, Download]
