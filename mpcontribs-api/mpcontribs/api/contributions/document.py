from flask_mongoengine import Document
from mongoengine import fields
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.structures.document import Structures


class Contributions(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, regex=__project_regex__,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    identifier = fields.StringField(
        required=True, help_text="material/composition identifier"
    )
    data = fields.DictField(help_text='free-form data to be shown in Contribution Card')
    structures = fields.ListField(fields.ReferenceField(Structures))
    tables = fields.ListField(fields.ReferenceField(Tables))
    meta = {
        'collection': 'contributions',
        'indexes': ['identifier', 'project', {'fields': ['project', 'identifier']}]
    }
