from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

class Tables(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    __objectid_regex__ = '^[a-f\d]{24}$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, regex = __project_regex__,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)"
    )
    identifier = fields.StringField(
        required=True, help_text="material/composition identifier"
    )
    name = fields.StringField(required=True, help_text="table name")
    cid = fields.StringField(
        min_length=24, max_length=24, required=True, regex = __objectid_regex__,
        help_text=f"Contribution ID (valid format: `{__objectid_regex__}`)"
    )
    columns = fields.ListField(
        fields.StringField(), required=True, help_text="column names"
    )
    data = fields.ListField(
        fields.ListField(fields.StringField()),
        required=True, help_text="table rows"
    )
    meta = {
        'collection': 'tables',
        'indexes': ['identifier', 'project', 'cid', 'name']
    }
