from flask import Blueprint
from pymatgen import Structure
from pymatgen.io.cif import CifWriter
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.structures.document import Structures

structures = Blueprint("structures", __name__)


class StructureView(SwaggerView):

    def get(self, sid):
        """Retrieve single structures in Pymatgen format.
        ---
        operationId: get_entry
        parameters:
            - name: sid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: Structure ID (ObjectId)
        responses:
            200:
                description: single structure
                schema:
                    $ref: '#/definitions/StructuresSchema'
        """
        entry = Structures.objects.no_dereference().get(id=sid)
        return self.marshal(entry)


class CifView(SwaggerView):

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
                    type: string
        """
        entry = Structures.objects.no_dereference().get(id=sid)
        structure = Structure.from_dict(entry.to_mongo())
        return CifWriter(structure, symprec=1e-10).__str__()


single_view = StructureView.as_view(StructureView.__name__)
structures.add_url_rule('/<string:sid>', view_func=single_view,
                        methods=['GET'])  # , 'PUT', 'PATCH', 'DELETE'])

cif_view = CifView.as_view(CifView.__name__)
structures.add_url_rule('/<string:sid>.cif', view_func=cif_view, methods=['GET'])
