# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch, Download
from flask import Blueprint, request

from mpcontribs.api import FILTERS
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures, make_cif

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
structures = Blueprint("structures", __name__, template_folder=templates)


class StructuresResource(Resource):
    document = Structures
    filters = {
        "id": [ops.In, ops.Exact],
        "md5": [ops.In, ops.Exact],
        "name": FILTERS["STRINGS"],
        "sites": [ops.Size]
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

    def get_queryset(self):
        # The CIF is generated on the fly from lattice/sites/charge (see `cif`
        # below), so make sure those fields are loaded whenever `cif` is
        # requested, even if the caller only asked for `cif` itself.
        qs = super().get_queryset()
        requested = self.get_requested_fields(params=self.params)
        if "cif" in requested:
            qs = qs.only("name", "lattice", "sites", "charge")
        return qs

    def cif(self, obj):
        # Computed-field override: shadows the stored `cif` on every read and
        # regenerates it from the canonical structure data, honoring the
        # `symmetrize` query parameter (default True).
        if not obj.sites or not obj.lattice:
            return None

        symmetrize = request.args.get("symmetrize", "true").lower() not in (
            "false",
            "0",
            "no",
        )
        d = {"lattice": obj.lattice, "sites": obj.sites}
        if obj.charge is not None:
            d["charge"] = obj.charge

        return make_cif(d, symmetrize=symmetrize)


class StructuresView(SwaggerView):
    resource = StructuresResource
    methods = [Fetch, BulkFetch, Download]
