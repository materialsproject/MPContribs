#class NoEmailString(fields.Raw):
#    def format(self, value):
#        return ' '.join(value.split()[:2])
#
#    '_id': fields.String(
#        readOnly=True, required=True,
#        description='unique contribution identifier (bson.ObjectId)',
#        example='5a862206d4f1443a18fab255'
#    ),
#    'identifier': fields.String(
#        required=True, example='mp-2715',
#        description='material/composition identifier',
#    ),
#    'project': fields.String(
#        required=True, example='dtu', readOnly=True,
#        description='project slug',
#    ),
#    'collaborators': fields.List(
#        NoEmailString(example='Patrick Huck <phuck@lbl.gov>'),
#        required=True, description='list of collaborators (emails stripped)'
#    ),
#    #'content': fields.Nested( # TODO from project schema (see above)
#    #    content, required=True,
#    #    description='free-form content of the contribution'
#    #)
#}, mask='{_id,identifier,collaborators}')

from marshmallow_mongoengine import ModelSchema
from mpcontribs.api.app import db

class Content(db.EmbeddedDocument):
    data = db.DynamicField()

class Collaborator(db.EmbeddedDocument):
    name = db.StringField(required=True)
    email = db.EmailField(required=True)

class Contribution(db.DynamicDocument):
    _id = db.ObjectIdField(required=True)
    identifier = db.StringField(required=True)
    project = db.StringField(max_length=30, required=True)
    collaborators = db.EmbeddedDocumentListField(Collaborator, required=True)
    content = db.EmbeddedDocumentField(Content)
    meta = {
        'collection': 'contributions',
        'indexes': ['identifier', 'project']
    }

class ContributionSchema(ModelSchema):
    class Meta:
        model = Contribution
