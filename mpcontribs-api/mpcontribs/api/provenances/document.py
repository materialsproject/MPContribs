from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

class Urls(DynamicEmbeddedDocument):
    main = fields.StringField()

# DynamicDocument documents work in the same way as Document but any data /
# attributes set to them will also be saved
class Provenances(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, unique=True,
        regex = __project_regex__,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    title = fields.StringField(
        min_length=5, max_length=30, required=True, unique=True,
        help_text='(short) title for the project/dataset'
    )
    authors = fields.StringField(
        required=True, help_text='comma-separated list of authors'
    )
    description = fields.StringField(
        min_length=5, max_length=1500, required=True,
        help_text='brief description of the project'
    )
    urls = fields.EmbeddedDocumentField(
        Urls, required=True, help_text='list of URLs for references'
    )
    # TODO permissions MapField
    # is required on POST but should never be returned on GET (write-only)
    meta = {
        'collection': 'provenances', 'indexes': [{
            'fields': ['$title', "$description", "$authors"],
        }, 'project']
    }
