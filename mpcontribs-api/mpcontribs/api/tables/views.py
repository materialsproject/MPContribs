# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch
from flask_mongorest.exceptions import UnknownFieldError
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
tables = Blueprint("tables", __name__, template_folder=templates)


class TablesResource(Resource):
    document = Tables
    filters = {
        "id": [ops.In, ops.Exact],
        "name": [ops.In, ops.Exact, ops.Contains],
        "columns": [ops.IContains],
        "md5": [ops.In, ops.Exact],
    }
    fields = ["id", "name"]
    allowed_ordering = ["name"]
    paginate = True
    default_limit = 10
    max_limit = 100
    fields_to_paginate = {"data": [20, 1000]}

    @staticmethod
    def get_optional_fields():
        return ["columns", "data", "md5", "total_data_rows", "total_data_pages"]

    def value_for_field(self, obj, field):
        if field == "total_data_pages":
            per_page_default = self.fields_to_paginate["data"][0]
            per_page = int(self.params.get("data_per_page", per_page_default))
            total_data_pages = int(obj.total_data_rows / per_page)
            total_data_pages += bool(obj.total_data_rows % per_page)
            return total_data_pages
        else:
            raise UnknownFieldError


class TablesView(SwaggerView):
    resource = TablesResource
    methods = [Fetch, BulkFetch]
