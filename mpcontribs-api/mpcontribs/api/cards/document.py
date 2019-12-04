from flask_mongoengine import Document
from mongoengine import fields


class Cards(Document):
    __project_regex__ = '^[a-zA-Z0-9_]+$'
    project = fields.StringField(
        min_length=3, max_length=30, required=True, regex=__project_regex__,
        help_text="project name/slug (valid format: `{}`)".format(
            __project_regex__
        )
    )
    is_public = fields.BooleanField(
        required=True, default=False, help_text='public or private card'
    )
    html = fields.StringField(required=True, default='', help_text="embeddable html code")
    meta = {'collection': 'cards', 'indexes': ['project', 'is_public']}
