from flask_mongoengine import Document
from mongoengine.fields import StringField, ObjectIdField, BooleanField, DictField, ListField


class Structures(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = StringField(
        min_length=3, max_length=30, required=True, regex=__project_regex__,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)"
    )
    identifier = StringField(
        required=True, help_text="material/composition identifier"
    )
    name = StringField(
        required=True, unique_with='cid', help_text="table name"
    )
    cid = ObjectIdField(
        required=True, help_text="Contribution ID"
    )
    is_public = BooleanField(
        required=True, default=False, help_text='public or private structure'
    )
    lattice = DictField(required=True, help_text="lattice")
    sites = ListField(
        DictField(), required=True, help_text="sites"
    )
    meta = {
        'collection': 'structures', 'indexes': [
            'identifier', 'project', 'cid', 'name', 'is_public',
            {'fields': ['cid', 'name'], 'unique': True}
        ]
    }
