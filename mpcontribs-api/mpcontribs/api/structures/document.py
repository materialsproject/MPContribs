from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import StringField, DictField, ListField, LazyReferenceField, BooleanField
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions


class Structures(Document):
    project = LazyReferenceField(Projects, passthrough=True, reverse_delete_rule=CASCADE)
    contribution = LazyReferenceField(Contributions, passthrough=True, reverse_delete_rule=CASCADE)
    is_public = BooleanField(required=True, default=False, help_text='public/private structure')
    name = StringField(required=True, help_text="table name")
    lattice = DictField(required=True, help_text="lattice")
    sites = ListField(DictField(), required=True, help_text="sites")
    meta = {'collection': 'structures', 'indexes': ['is_public', 'name']}
