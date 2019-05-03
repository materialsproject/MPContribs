from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument, CASCADE
from mpcontribs.api.tables.document import Tables

class Collaborator(fields.EmbeddedDocument):
    name = fields.StringField(required=True)
    email = fields.StringField(required=True)
    # TODO hide email field?
    # TODO use EmailField but "email format is not registered with bravado-core"
    # https://bravado-core.readthedocs.io/en/stable/formats.html#formats

class Contents(DynamicEmbeddedDocument):
    data = fields.DictField(
        required=True,
        help_text='data to be shown in Contribution Card'
    )
    structures = fields.DictField(help_text='contributed structures')
    tables = fields.ListField(fields.ReferenceField(Tables))
    # reverse_delete_rule=CASCADE not supported for EmbeddedDocuments
    # TODO other mp_level01_titles?

# DynamicDocument documents work in the same way as Document but any data /
# attributes set to them will also be saved
class Contributions(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, regex = __project_regex__,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    identifier = fields.StringField(
        required=True, help_text="material/composition identifier"
    )
    collaborators = fields.EmbeddedDocumentListField(
        Collaborator, required=True,
        help_text='list of collaborators (emails stripped)'
    )
    content = fields.EmbeddedDocumentField(
        Contents, required=True,
        help_text='free-form content of the contribution'
    )
    meta = {
        'collection': 'contributions',
        'indexes': ['identifier', 'project', {'fields': ['project', 'identifier']}]
    }
