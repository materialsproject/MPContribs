# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch, Download
from flask_mongorest.exceptions import UnknownFieldError
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables, Attributes, Labels

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
tables = Blueprint("tables", __name__, template_folder=templates)


class LabelsResource(Resource):
    document = Labels


class AttributesResource(Resource):
    document = Attributes
    related_resources = {"labels": LabelsResource}


class TablesResource(Resource):
    document = Tables
    related_resources = {"attrs": AttributesResource}
    filters = {
        "id": [ops.In, ops.Exact],
        "name": [ops.In, ops.Exact, ops.Contains],
        "columns": [ops.IContains],
        "md5": [ops.In, ops.Exact],
    }
    fields = ["id", "name", "md5"]
    allowed_ordering = ["name"]
    paginate = True
    default_limit = 10
    max_limit = 100
    fields_to_paginate = {"data": [20, 1000]}
    download_formats = ["json"]

    @staticmethod
    def get_optional_fields():
        return [
            "attrs",
            "index",
            "columns",
            "data",
            "total_data_rows",
            "total_data_pages",
        ]

    def value_for_field(self, obj, field):
        if field == "total_data_pages":
            if obj.total_data_rows is None:
                return None

            per_page_default = self.fields_to_paginate["data"][0]
            per_page = int(self.params.get("data_per_page", per_page_default))
            total_data_pages = int(obj.total_data_rows / per_page)
            total_data_pages += bool(obj.total_data_rows % per_page)
            return total_data_pages
        else:
            raise UnknownFieldError


class TablesView(SwaggerView):
    resource = TablesResource
    methods = [Fetch, BulkFetch, Download]
