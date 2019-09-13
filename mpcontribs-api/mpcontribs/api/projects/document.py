from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

# DynamicDocument documents work in the same way as Document but any data /
# attributes set to them will also be saved
class Projects(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, regex=__project_regex__, primary_key=True,
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
    urls = fields.DictField(
        required=True, help_text='list of URLs for references'
    )
    other = fields.DictField(help_text='other information')
    meta = {'collection': 'projects'}
