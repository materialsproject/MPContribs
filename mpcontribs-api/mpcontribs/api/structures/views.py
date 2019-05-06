from flask import Blueprint, request, current_app
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

single_view = StructureView.as_view(StructureView.__name__)
structures.add_url_rule('/<string:sid>', view_func=single_view,
                        methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])
