from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

#class NoEmailString(fields.Raw):
#    def format(self, value):
#        return ' '.join(value.split()[:2])

class Collaborator(fields.EmbeddedDocument):
    name = fields.StringField(required=True)
    email = fields.EmailField(required=True)

class Contents(DynamicEmbeddedDocument):
    data = fields.DictField(
        required=True,
        help_text='data to be shown in Contribution Card'
    )

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
    build = fields.BooleanField(
        help_text="whether to (re-)build a derived materials/compositions \
        notebook doc from this contribution - internal use only"
    )
    collaborators = fields.EmbeddedDocumentListField(
        Collaborator, required=True,
        help_text='list of collaborators (emails stripped)'
    ),
    content = fields.EmbeddedDocumentField(
        Contents, required=True,
        help_text='free-form content of the contribution'
    )
    meta = {
        'collection': 'contributions',
        'indexes': ['identifier', 'project']
    }
