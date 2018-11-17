from flask import Flask
from flask_rebar import errors, Rebar
from flask_mongoengine import MongoEngine
from flask_marshmallow import Marshmallow

ma = Marshmallow()
db = MongoEngine()
rebar = Rebar()

registry = rebar.create_handler_registry(prefix='/v1')

class Provenance(db.Document):
    #_id = db.ObjectIdField(required=True, unique=True)
    title = db.StringField(max_length=30, required=True, unique=True)
    authors = db.StringField(required=True)
    description = db.StringField(required=True)
    urls = db.ListField(db.DictField(), required=True)
    project = db.StringField(max_length=30, required=True, unique=True)
    meta = {
        'collection': 'provenances',
        'indexes': ['title', 'project']
    }

class Content(db.EmbeddedDocument):
    data = db.DynamicField()

class Collaborator(db.EmbeddedDocument):
    name = db.StringField(required=True)
    email = db.EmailField(required=True)

class Contribution(db.DynamicDocument):
    _id = db.ObjectIdField(required=True, unique=True)
    identifier = db.StringField(required=True)
    project = db.StringField(max_length=30, required=True)
    collaborators = db.EmbeddedDocumentListField(Collaborator, required=True)
    content = db.EmbeddedDocumentField(Content)
    meta = {
        'collection': 'contributions',
        'indexes': ['identifier', 'project']
    }

class ProvenanceSchema(ma.Schema):
    class Meta:
        model = Provenance

class ContributionSchema(ma.Schema):
    class Meta:
        model = Contribution

@registry.handles(
    rule='/provenances/<project>',
    method='GET', marshal_schema=ProvenanceSchema(),
)
def get_provenance(project):
    """retrieve provenance for a project"""
    # The query string has already been validated by `query_string_schema`
    #project = rebar.validated_args.get('project') # TODO
    provenance = {} # TODO db mongoengine query
    # The response will be marshaled by `marshal_schema`
    return provenance

def create_app(name):
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma.init_app(app)
    db.init_app(app)
    rebar.init_app(app)
    return app

if __name__ == '__main__':
    create_app(__name__).run()
