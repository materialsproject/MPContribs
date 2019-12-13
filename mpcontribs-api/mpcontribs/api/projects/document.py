from flask_mongoengine import Document
from mongoengine.fields import StringField, BooleanField, DictField, URLField, MapField


class Projects(Document):
    __project_regex__ = '^[a-zA-Z0-9_]{3,31}$'
    project = StringField(
        min_length=3, max_length=30, regex=__project_regex__, primary_key=True,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)"
    )
    is_public = BooleanField(required=True, default=False, help_text='public/private project')
    title = StringField(
        min_length=5, max_length=40, required=True, unique=True,
        help_text='(short) title for the project/dataset'
    )
    authors = StringField(
        required=True, help_text='comma-separated list of authors'
    )
    description = StringField(
        min_length=5, max_length=1500, required=True,
        help_text='brief description of the project'
    )
    urls = MapField(URLField(), required=True, help_text='list of URLs for references')
    other = DictField(help_text='other information')
    meta = {'collection': 'projects', 'indexes': ['is_public']}
