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
from mpcontribs.api.structures.document import Structures
from mpcontribs.api.tables.document import Tables

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
contributions = Blueprint("contributions", __name__, template_folder=templates)
exclude = r'[^$.\s_~`^&(){}[\]\\;\'"/]'


class ContributionsResource(Resource):
    document = Contributions
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

    def value_for_field(self, obj, field):
        if not field.startswith("structures") and not field.startswith("tables"):
            raise UnknownFieldError

        field_split = field.split(".")
        field_len = len(field_split)
        if field_len > 2:
            raise UnknownFieldError

        # add structures and tables info to response if requested
        from mpcontribs.api.structures.views import StructuresResource
        from mpcontribs.api.tables.views import TablesResource

        mask = ["id", "label", "name"]
        # return full structures/tables only if download requested
        full = bool(
            self.view_method == Download and self.params.get("_fields") == "_all"
        )
        fmt = self.params.get("format")
        kwargs = dict(contribution=obj.id)
        if field_len == 2:
            # requested structure/table(s) for specific label
            kwargs["label"] = field_split[1]

        if field.startswith("structures"):
            res = StructuresResource(view_method=self.view_method)
            if full and fmt == "json":
                mask += ["lattice", "sites", "charge", "klass", "module"]
            objects = Structures.objects.only(*mask)
        else:
            res = TablesResource(view_method=self.view_method)
            # TODO adjust mask for full json format
            objects = Tables.objects.only(*mask)

        objects = objects.filter(**kwargs).order_by("-id")
        result = defaultdict(list)
        for o in objects:
            os = res.serialize(o, fields=mask)
            # TODO res.value_for_field(o, "cif") if fmt == "csv" and field.startswith("structures")
            result[os.pop("label")].append(os)

        ret = result if field_len == 1 else list(result.values())[0]
        obj.update(**{f"set__{field.replace('.', '__')}": ret})
        return ret


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
