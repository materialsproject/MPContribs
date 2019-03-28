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
        https://docs.mongodb.com/manual/text-search/. Retrieve a provenance \
        entry via the `project` query parameter.
        ---
        parameters:
            - name: search
              in: query
              type: string
              description: string to search for in title, authors, description
            - name: project
              in: query
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              description: project identifier (name/slug)
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
        if 'search' in request.args:
            entries = objects.search_text(request.args['search'])
        if 'project' in request.args:
            entries = objects.get(project=request.args['project'])
        else:
            entries = objects.all()
        return self.marshal(entries)

    # TODO: only staff can start new project (post new provenance entry)
    def post(self):
        """Create a new provenance entry.
        Only MP staff can submit a new/non-existing project (or use POST
        endpoints in general). The staff member's email address will be set as
        the first readWrite entry in the permissions dict.
        """
        pass

    # TODO: only emails with readWrite permissions can use methods below
    def put(self, project):
        """Replace a project's provenance entry"""
        # TODO id/project are read-only
        pass

    def patch(self, project):
        """Partially update a project's provenance entry"""
        schema = self.Schema(dump_only=('id', 'project')) # id/project read-only
        schema.opts.model_build_obj = False
        payload = schema.load(request.json, partial=True)
        if payload.errors:
            return payload.errors # TODO raise JsonError 400?
        # set fields defined in model
        if 'urls' in payload.data:
            urls = payload.data.pop('urls')
            payload.data.update(dict(
                ('urls__'+key, getattr(urls, key)) for key in urls
            ))
        # set dynamic fields for urls
        for key, url in request.json.get('urls', {}).items():
            payload.data['urls__'+key] = url
        return payload.data
        #Provenances.objects(project=project).update(**payload.data)

    def delete(self, project):
        """Delete a project's provenance entry"""
        # TODO should also delete all contributions
        pass

# url_prefix added in register_blueprint
provenances.add_url_rule(
    '/', view_func=ProvenancesView.as_view(ProvenancesView.__name__),
    methods=['GET']#, 'POST', 'PUT', 'PATCH', 'DELETE']
)
