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
from mpcontribs.api.structures.document import Structures
from mpcontribs.api.projects.views import ProjectsResource
from mpcontribs.api.contributions.views import ContributionsResource

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
structures = Blueprint("structures", __name__, template_folder=templates)


class StructuresResource(Resource):
    document = Structures
    related_resources = {'project': ProjectsResource, 'contribution': ContributionsResource}
    save_related_fields = ['project', 'contribution']
    filters = {
        'project': [ops.In, ops.Exact],
        'contribution__identifier': [ops.In, ops.Contains, ops.Exact],
        'contribution__is_public': [ops.Boolean],
        'name': [ops.Exact, ops.Contains]
    }
    fields = ['id', 'project', 'contribution', 'name']
    allowed_ordering = ['name']
    paginate = True
    default_limit = 10
    max_limit = 20
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['lattice', 'sites', 'cif']

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
