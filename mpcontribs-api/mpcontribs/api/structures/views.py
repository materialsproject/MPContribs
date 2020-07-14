# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.methods import *
from flask import Blueprint
from pymatgen import Structure
from pymatgen.io.cif import CifWriter
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures
from mpcontribs.api.contributions.views import ContributionsResource

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
structures = Blueprint("structures", __name__, template_folder=templates)


class StructuresResource(Resource):
    document = Structures
    related_resources = {"contribution": ContributionsResource}
    filters = {
        "id": [ops.In, ops.Exact],
        "contribution": [ops.In, ops.Exact],
        "is_public": [ops.Boolean],
        "name": [ops.In, ops.Exact, ops.Contains],
    }
    fields = ["id", "contribution", "is_public", "name", "label"]
    rename_fields = {"klass": "@class", "module": "@module"}
    allowed_ordering = ["is_public", "name"]
    paginate = True
    default_limit = 10
    max_limit = 100
    # fields_to_paginate = {'sites': [20, 100]}  # TODO

    @staticmethod
    def get_optional_fields():
        return ["lattice", "sites", "klass", "module", "charge", "cif"]

    def value_for_field(self, obj, field):
        # add cif key to response if requested
        if field == "cif":
            # make sure to have full structure object available
            s = Structures.objects.get(id=obj.id)
            fields = self.get_optional_fields()[:-1]
            structure = Structure.from_dict(self.serialize(s, fields=fields))
            cif = CifWriter(structure, symprec=1e-10).__str__()
            s.update(set__cif=cif)
            return cif
        else:
            raise UnknownFieldError


class StructuresView(SwaggerView):
    resource = StructuresResource
    methods = [Fetch, BulkCreate, Delete, Update, BulkFetch, BulkUpdate]
