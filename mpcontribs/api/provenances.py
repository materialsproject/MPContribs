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

from flask import g
import marshmallow as ma
from marshmallow_mongoengine import ModelSchema
from flask_mongoengine import Document, DynamicDocument
from mongoengine import fields, DynamicEmbeddedDocument, EmbeddedDocumentField

class Urls(DynamicEmbeddedDocument):
    main = fields.URLField(required=True)
    # TODO make sure all fields show up in response

class Provenance(DynamicDocument): # TODO use Document?
    _id = fields.ObjectIdField(required=True) # `id` to avoid 'auto_id_0' in the schema?
    title = fields.StringField(max_length=30, required=True, unique=True)
    authors = fields.StringField(required=True)
    description = fields.StringField(required=True)
    urls = EmbeddedDocumentField(Urls, required=True)
    project = fields.StringField(max_length=30, required=True, unique=True)
    meta = {
        'collection': 'provenances',
        'indexes': ['title', 'project']
    }

class ProvenanceSchema(ModelSchema):
    class Meta:
        model = Provenance

class GetProvenanceQuerySchema(ma.Schema):
    project = ma.fields.String(max_length=30)
    title = ma.fields.String(max_length=30)

def get_provenance():
    """retrieve provenance for a project (via slug or title)"""
    valid_args = g.validated_args
    return Provenance.objects.get_or_404(**valid_args)

def get_projects():
    """retrieve list of all available project slugs"""
    #print(Provenance.objects.get_or_404())
    return 'hello world'
