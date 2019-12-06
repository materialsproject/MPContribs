from flask_mongoengine import Document
from mongoengine.fields import StringField, BooleanField, DictField


class Projects(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = StringField(
        min_length=3, max_length=30, regex=__project_regex__, primary_key=True,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    is_public = BooleanField(
        required=True, default=False, help_text='public or private project'
    )
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
    urls = DictField(required=True, help_text='list of URLs for references')
    other = DictField(help_text='other information')
    meta = {'collection': 'projects', 'indexes': ['is_public']}
