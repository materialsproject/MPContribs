import marshmallow as ma
from marshmallow_mongoengine import ModelSchema
from flask_mongoengine import Document, DynamicDocument
from mongoengine import fields, DynamicEmbeddedDocument, EmbeddedDocumentField
from mongoengine.queryset import DoesNotExist
from flask import Blueprint, jsonify, request
from flasgger import SwaggerView

provenances = Blueprint("provenances", __name__)

class Urls(DynamicEmbeddedDocument):
    main = fields.StringField(required=True)
    # TODO URL validation?
    # TODO make sure all fields show up in response


class Provenance(DynamicDocument):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, unique=True,
        regex = __project_regex__,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    title = fields.StringField(
        min_length=5, max_length=30, required=True, unique=True,
        help_text='(short) title for the project/dataset'
    )
    authors = fields.StringField(
        required=True, help_text='comma-separated list of authors'
    )
    description = fields.StringField(
        min_length=5, max_length=1500, required=True,
        help_text='brief description of the project'
    )
    urls = EmbeddedDocumentField(
        Urls, required=True, help_text='list of URLs for references'
    )
    meta = {
        'collection': 'provenances', 'indexes': [{
            'fields': ['$title', "$description", "$authors"],
        }, 'project']
    }

    def __str__(self):
        return '<Provenance(project={self.project!r})>'.format(self=self)

class ProvenanceSchema(ModelSchema):
    class Meta:
        model = Provenance
        ordered = True

class ProvenancesView(SwaggerView):
    definitions = {'ProvenanceSchema': ProvenanceSchema}
    tags = ['provenances']

    def marshal(self, entries):
        return jsonify(ProvenanceSchema().dump(entries, many=True).data)

    def get(self):
        """Retrieve and search provenance information for all projects.
        If a string is provided  via the search parameter, `title`, \
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
                description: list of provenance entries
                schema:
                    $ref: '#/definitions/ProvenanceSchema'
                examples:
                    entries: |
                        [{
                            "authors": "P. Huck, K. Persson",
                            "description": "Bandgaps calculated ... electron affinity.",
                            "id": "5bef38d9aba702da481fe974",
                            "project": "dtu",
                            "title": "GLLB-SC Bandgaps",
                            "urls": { "main": "https://doi.org/10.1002/aenm.201400915" }
                        }, ...]
        """
        entries = Provenance.objects.search_text(request.args['search']) \
                if 'search' in request.args else Provenance.objects.all()
        return self.marshal(entries)

    def post(self):
        """Create a new provenance entry"""
        # validate ProvenanceSchema().load(args, partial=True)
        pass

class ProjectView(SwaggerView):
    definitions = {'ProvenanceSchema': ProvenanceSchema}
    tags = ['provenances']

    def marshal(self, entry):
        return jsonify(ProvenanceSchema().dump(entry).data)

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
        """
        try:
            entry = Provenance.objects.get(project=project)
        except DoesNotExist:
            return jsonify({project: 'DoesNotExist'}), 404
        return self.marshal(entry)

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

# url_prefix added in register_blueprint
provenances.add_url_rule(
    '/', view_func=ProvenancesView.as_view('provenances'), methods=['GET', 'POST']
)
provenances.add_url_rule(
    '/<string:project>',
    view_func=ProjectView.as_view('project'),
    methods=['GET', 'DELETE', 'PATCH', 'PUT']
)
