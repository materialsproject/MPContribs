from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import LazyReferenceField, BooleanField, StringField
from mpcontribs.api.projects.document import Projects


class Cards(Document):
    project = LazyReferenceField(
        Projects, passthrough=True, reverse_delete_rule=CASCADE,
        required=True, help_text="project this card belongs to"
    )
    is_public = BooleanField(required=True, default=False, help_text='public or private card')
    html = StringField(required=True, default='', help_text="embeddable html code")
    meta = {'collection': 'cards', 'indexes': ['project', 'is_public']}
