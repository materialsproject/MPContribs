from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.provenances.document import Provenances

provenances = Blueprint("provenances", __name__)

class ProvenancesView(SwaggerView):
    """defines methods for API operations with provenances"""

    def get(self):
        """Retrieve (and optionally filter) provenances.
        If a string is provided via the search parameter, `title`, \
        `description`, and `authors` are searched using a MongoEngine/MongoDB \
        text index. Provide a space-separated list to the search query \
        parameter to search for multiple words. For more, see \
        https://docs.mongodb.com/manual/text-search/.
        ---
        parameters:
            - name: search
              in: query
              type: string
              description: string to search for in title, authors, description
        responses:
            200:
                description: list of provenance entries with fields project, title, and authors
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ProvenancesSchema'
                examples:
                    entries: |
                        [ {
                            "authors": "J. Vieten, B. Bulfin, D. Guban, L. Zhu, P. Huck, M. Horton, K. Persson, M. Roeb, C. Sattler",
                            "id": "5bef38a0aba702da481fe970",
                            "project": "redox_thermo_csp",
                            "title": "RedoxThermoCSP"
                        }, {
                            "authors": "A.T. N`Diaye, R. Ott, A.A. Baker",
                            "id": "5bef38b1aba702da481fe971",
                            "project": "als_beamline",
                            "title": "CuCoCe Project"
                        }, ... ]
        """
        mask = ['project', 'title', 'authors'] # TODO make HEADER option?
        objects = Provenances.objects.only(*mask)
        entries = objects.search_text(request.args['search']) \
                if 'search' in request.args else objects.all()
        return self.marshal(entries)

    def post(self):
        """Create a new provenance entry.
        Only MP staff can submit a new/non-existing project (or use POST
        endpoints in general). The staff member's email address will be set as
        the first readWrite entry in the permissions dict.
        """
        from flask_json import JsonError
        unmarshalled = self.Schema().load(request.json)
        if unmarshalled.errors:
            raise JsonError(400, )
            return unmarshalled.errors
        return unmarshalled.data

class ProjectsView(SwaggerView):
    """defines methods for API operations with project provenance"""

    def get(self, project):
        """Retrieve a project/dataset's provenance information.
        ---
        parameters:
            - name: project
              in: path
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: project identifier (name/slug)
        responses:
            200:
                description: provenance entry
                schema:
                    $ref: '#/definitions/ProvenancesSchema'
                examples:
                    entry: |
                        {
                            "authors": "P. Huck, K. Persson",
                            "description": "Bandgaps calculated ... electron affinity.",
                            "id": "5bef38d9aba702da481fe974",
                            "project": "dtu",
                            "title": "GLLB-SC Bandgaps",
                            "urls": { "main": "https://doi.org/10.1002/aenm.201400915" }
                        }
        """
        entry = Provenances.objects.get(project=project)
        return self.marshal(entry)

    # TODO: only emails with readWrite permissions can use methods below
    def put(self, project):
        """Update a project's provenance entry"""
        pass

    def patch(self, project):
        """Partially update a project's provenance entry"""
        pass

    def delete(self, project):
        """Delete a project's provenance entry"""
        # TODO should also delete all contributions
        pass

# url_prefix added in register_blueprint
provenances.add_url_rule(
    '/', view_func=ProvenancesView.as_view(ProvenancesView.__name__),
    methods=['GET']#, 'POST']
)
provenances.add_url_rule(
    '/<string:project>',
    view_func=ProjectsView.as_view(ProjectsView.__name__),
    methods=['GET']#, 'DELETE', 'PATCH', 'PUT']
)
