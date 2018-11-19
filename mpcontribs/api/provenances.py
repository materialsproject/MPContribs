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
    # TODO URL validation?
    # TODO make sure all fields show up in response

class Provenance(DynamicDocument):
    project = fields.StringField(
        min_length=3, max_length=30, required=True, unique=True,
        regex = '^[a-zA-Z0-9_]+$', help_text="help text for project field"
    )
    title = fields.StringField(
        min_length=5, max_length=30, required=True, unique=True
    )
    authors = fields.StringField(required=True)
    description = fields.StringField(
        min_length=50, max_length=250, required=True
    )
    urls = EmbeddedDocumentField(Urls, required=True)
    meta = {
        'collection': 'provenances', 'indexes': [{
            'fields': ['$title', "$description", "$authors"],
        }, 'project']
    }

    def __repr__(self):
        return '<Provenance(project={self.project!r})>'.format(self=self)

class ProvenanceSchema(ModelSchema):
    class Meta:
        model = Provenance
        ordered = True

class ProvenanceView(SwaggerView):
    summary = "Operations for provenance info of materials data contributed to MP"
    tags = ['provenances']
    parameters = ProvenanceSchema # default (can be overidden in methods below)

    def get(self, project=None):
        """Retrieve a project/dataset's provenance information.
        Provenance information for a project includes `title`, `authors`, \
        `description`, and `urls`. Without a project name/slug provided in the \
        URL, this endpoint retrieves a list of provenance entries for projects \
        matching the other query parameters (see body/schema description below). \
        For the parameters `title`, `description`, and `authors` a search over
        the MongoEngine/MongoDB text index is being used (see \
        https://docs.mongodb.com/manual/text-search/)
        ---
        parameters:
            - name: project
              in: path
              type: string
              description: project identifier (name/slug)
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
        data, errors = ProvenanceSchema().load(request.args, partial=True)
        if errors:
            return jsonify(errors), 404
        project = data.project if 'project' in data else project
        print(project, data)
        #    provenance = Provenance.objects.get_or_404(project=project)
        # TODO text search in descriptions, authors, titles
        # db.provenances.find({ $text: { $search: "bandgap phases" } })
        return jsonify(project)
        # many=True to validate list
        #ProvenanceSchema().dump(provenance).data
        #return jsonify(provenance)

    def post(self):
        """Create a new provenance entry"""
        pass

    def put(self, project):
        """Update a project's provenance entry"""
        pass

    def patch(self, project):
        """Partially update a project's provenance entry"""
        pass

    def delete(self, project):
        """Delete a project's provenance entry"""
        pass

# Flask-RESTful/plus
# api.add_resource(UserAPI, '/<userId>', '/<userId>/<username>', endpoint = 'user')
view_func = ProvenanceView.as_view('provenance')
# url_prefix added in register_blueprint
provenances.add_url_rule('/', view_func=view_func, methods=['POST'])
provenances.add_url_rule(
    '/<string:project>', view_func=view_func,
    methods=['GET', 'DELETE', 'PATCH', 'PUT']
)
