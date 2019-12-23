import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask import Blueprint
from pymatgen import Structure
from pymatgen.io.cif import CifWriter
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures, Lattice, Site, Specie, Properties
from mpcontribs.api.contributions.views import ContributionsResource

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
structures = Blueprint("structures", __name__, template_folder=templates)


class LatticeResource(Resource):
    document = Lattice


class SpecieResource(Resource):
    document = Specie


class PropertiesResource(Resource):
    document = Properties


class SiteResource(Resource):
    document = Site
    related_resources = {'species': SpecieResource, 'properties': PropertiesResource}


class StructuresResource(Resource):
    document = Structures
    related_resources = {
        'contribution': ContributionsResource,
        'lattice': LatticeResource, 'sites': SiteResource
    }
    filters = {
        'contribution': [ops.Exact],
        'is_public': [ops.Boolean],
        'name': [ops.Exact, ops.Contains]
    }
    fields = ['id', 'contribution', 'is_public', 'name']
    rename_fields = {'klass': '@class', 'module': '@module'}
    allowed_ordering = ['is_public', 'name']
    paginate = True
    default_limit = 10
    max_limit = 20
    bulk_update_limit = 100
    # fields_to_paginate = {'sites': [20, 100]}  # TODO

    @staticmethod
    def get_optional_fields():
        return ['lattice', 'sites', 'klass', 'module', 'charge', 'cif']

    def value_for_field(self, obj, field):
        # add cif key to response if requested
        if field == 'cif':
            s = Structures.objects.get(id=obj.id)
            structure = Structure.from_dict(s.to_mongo())
            return CifWriter(structure, symprec=1e-10).__str__()
        else:
            raise UnknownFieldError


class StructuresView(SwaggerView):
    resource = StructuresResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]
