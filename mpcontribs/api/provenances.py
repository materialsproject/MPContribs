#'title': fields.String(
#    example='GLLB-SC Bandgaps',
#    description='(short) title for the project/dataset',
#),
#'description': fields.String(
#    description='Brief description of the project',
#),
#'authors': fields.String(
#    example='P. Huck, K. Persson',
#    description='comma-separated list of authors',
#),
#'urls': fields.Nested(
#    required=True, description='list of URLs for references'
#)

import marshmallow as ma
from marshmallow_mongoengine import ModelSchema
from flask_mongoengine import Document, DynamicDocument
from mongoengine import fields, DynamicEmbeddedDocument, EmbeddedDocumentField
from flask import Blueprint, jsonify, request
from flasgger import SwaggerView

provenances = Blueprint("provenances", __name__)

class Urls(DynamicEmbeddedDocument):
    main = fields.StringField(required=True)
    # TODO make sure all fields show up in response

class Provenance(DynamicDocument): # TODO use Document?
    title = fields.StringField(
        max_length=30, required=True, unique=True,
    )
    authors = fields.StringField(required=True)
    description = fields.StringField(required=True)
    urls = EmbeddedDocumentField(Urls, required=True)
    project = fields.StringField(max_length=30, required=True, unique=True)
    meta = {
        'collection': 'provenances',
        'indexes': ['title', 'project'],
    }

class ProvenanceSchema(ModelSchema):
    class Meta:
        model = Provenance

class ProvenanceView(SwaggerView):
    # TODO tags, description
    definitions = {'ProvenanceSchema': ProvenanceSchema}
    #validation = True # for request.json only (PUT, POST, ...)

    def get(self, project=None):
        """Retrieve provenance information for contributed projects/datasets.
        Provenance information for a project includes `title`, `authors`,
        `description`, and `urls`. Without a project name/slug provided in the
        URL, this endpoint retrieves a list of provenance entries for projects
        matching the query parameters.
        ---
        parameters:
            - name: project
              in: path
              type: string
              minLength: 3
              maxLength: 30
              pattern: '^[a-zA-Z0-9_]*$'
              description: project identifier (name/slug)
            - name: title
              in: query
              type: string
              description: search project titles
        responses:
            200:
                description: one or list of provenance entries
                schema:
                    $ref: '#/definitions/ProvenanceSchema'
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
                    list: [entry1, entry2, ...]
        """
        # TODO text search in descriptions, authors, titles
        project = request.parsed_data['path'].get('project')
        if project is not None:
            provenance = Provenance.objects.get_or_404(project=project)
        return jsonify(project)
        # TODO marshal the response
        #return jsonify(ProvenanceSchema().dump(provenance).data)

    def post(self):
        """POST /tickets - Creates a new ticket"""
        pass

    def put(self):
        """PUT /tickets/12 - Updates ticket #12"""
        pass

    def patch(self):
        """PATCH /tickets/12 - Partially updates ticket #12"""
        pass

    def delete(self):
        """DELETE /tickets/12 - Deletes ticket #12"""
        pass

# Flask-RESTful/plus
# api.add_resource(UserAPI, '/<userId>', '/<userId>/<username>', endpoint = 'user')
provenances.add_url_rule(
    '/<string:project>', # url_prefix added in register_blueprint
    view_func=ProvenanceView.as_view('provenance'),
    methods=['GET']
)
