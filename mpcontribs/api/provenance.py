#'title': fields.String(
#    example='GLLB-SC Bandgaps',
#    description='unique contribution identifier (bson.ObjectId)',
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

from marshmallow_mongoengine import ModelSchema
from flask_rebar import HandlerRegistry
from mongoengine import fields, DynamicEmbeddedDocument, EmbeddedDocumentField
from flask_mongoengine import Document, DynamicDocument

class Url(DynamicEmbeddedDocument):
    main = fields.URLField(required=True)

class Provenance(DynamicDocument): # TODO Document
    _id = fields.ObjectIdField(required=True)
    title = fields.StringField(max_length=30, required=True, unique=True)
    authors = fields.StringField(required=True)
    description = fields.StringField(required=True)
    urls = EmbeddedDocumentField(Url, required=True)
    project = fields.StringField(max_length=30, required=True, unique=True)
    meta = {
        'collection': 'provenances',
        'indexes': ['title', 'project']
    }

class ProvenanceSchema(ModelSchema):
    class Meta:
        model = Provenance

def get_provenance(project):
    """retrieve provenance for a project"""
    #project = rebar.validated_args.get('project')
    return Provenance.objects.get_or_404(project=project)
