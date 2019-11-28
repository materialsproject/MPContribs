from flask_mongoengine import Document
from mongoengine import fields


class Tables(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, regex=__project_regex__,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)"
    )
    identifier = fields.StringField(
        required=True, help_text="material/composition identifier"
    )
    name = fields.StringField(
        required=True, unique_with='cid', help_text="table name"
    )
    cid = fields.ObjectIdField(
        required=True, help_text="Contribution ID"
    )
    is_public = fields.BooleanField(
        required=True, default=False, help_text='public or private table'
    )
    columns = fields.ListField(
        fields.StringField(), required=True, help_text="column names"
    )
    data = fields.ListField(
        fields.ListField(fields.StringField()),
        required=True, help_text="table rows"
    )
    config = fields.DictField(help_text="graph config")
    meta = {
        'collection': 'tables', 'indexes': [
            'identifier', 'project', 'cid', 'name', 'is_public',
            {'fields': ['cid', 'name'], 'unique': True},
            {'fields': ['identifier', 'project', 'name'], 'unique': True}
        ]
    }
