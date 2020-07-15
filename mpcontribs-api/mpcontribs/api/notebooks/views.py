# -*- coding: utf-8 -*-
import os
import flask_mongorest

from flask import Blueprint
from flask_mongorest.methods import Fetch, BulkFetch
from flask_mongorest.resources import Resource

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)


class NotebooksResource(Resource):
    document = Notebooks
    fields = ["nbformat", "nbformat_minor", "metadata", "cells"]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch, BulkFetch]
