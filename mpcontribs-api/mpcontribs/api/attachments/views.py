# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch, Download
from flask_mongorest.exceptions import UnknownFieldError
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.attachments.document import Attachments

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
attachments = Blueprint("attachments", __name__, template_folder=templates)


class AttachmentsResource(Resource):
    document = Attachments
    filters = {
        "id": [ops.In, ops.Exact],
        "name": [ops.In, ops.Exact, ops.Contains],
        "mime": [ops.In, ops.Exact, ops.Contains],
        "md5": [ops.In, ops.Exact],
    }
    fields = ["id", "name", "mime", "md5"]
    allowed_ordering = ["name", "mime"]
    paginate = True
    default_limit = 10
    max_limit = 100
    download_formats = ["json", "csv"]

    @staticmethod
    def get_optional_fields():
        return ["content"]


class AttachmentsView(SwaggerView):
    resource = AttachmentsResource
    methods = [Fetch, BulkFetch, Download]
