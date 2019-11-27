import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update
from flask import Blueprint
from pymatgen import Structure
from pymatgen.io.cif import CifWriter

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
structures = Blueprint("structures", __name__, template_folder=templates)


class StructuresResource(Resource):
    document = Structures
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.Exact],
        'name': [ops.Exact],
        'cid': [ops.Exact]
    }
    fields = ['id', 'project', 'identifier', 'name', 'cid']
    allowed_ordering = ['project', 'identifier']
    paginate = True
    default_limit = 10
    max_limit = 20
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['lattice', 'sites']


class StructuresView(SwaggerView):
    resource = StructuresResource
    methods = [List, Fetch, Create, Delete, Update]


class CifView(SwaggerView):
    resource = StructuresResource

    def get(self, sid):
        """Retrieve structure for contribution in CIF format.
        ---
        operationId: get_cif
        parameters:
            - name: sid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: Structure ID (ObjectId)
        responses:
            200:
                description: structure in CIF format
                schema:
                    type: object
                    properties:
                        cif:
                            type: string
        """
        entry = Structures.objects.no_dereference().get(id=sid)
        structure = Structure.from_dict(entry.to_mongo())
        return {'cif': CifWriter(structure, symprec=1e-10).__str__()}


cif_view = CifView.as_view(CifView.__name__)
structures.add_url_rule('/<string:sid>.cif', view_func=cif_view, methods=['GET'])
