from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import StringField, BooleanField, DictField, LazyReferenceField
from mpcontribs.api.projects.document import Projects


class Contributions(Document):
    project = LazyReferenceField(Projects, passthrough=True, reverse_delete_rule=CASCADE)
    identifier = StringField(required=True, help_text="material/composition identifier")
    is_public = BooleanField(required=True, default=False, help_text='public/private contribution')
    data = DictField(help_text='free-form data to be shown in Contribution Card')
    meta = {'collection': 'contributions', 'indexes': ['project', 'identifier', 'is_public']}
