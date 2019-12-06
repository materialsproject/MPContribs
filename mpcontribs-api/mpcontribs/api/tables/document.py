from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import LazyReferenceField, StringField, ListField, DictField
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions


class Tables(Document):
    project = LazyReferenceField(Projects, passthrough=True, reverse_delete_rule=CASCADE)
    contribution = LazyReferenceField(Contributions, passthrough=True, reverse_delete_rule=CASCADE)
    name = StringField(required=True, help_text="table name")
    columns = ListField(StringField(), required=True, help_text="column names")
    data = ListField(ListField(StringField()), required=True, help_text="table rows")
    config = DictField(help_text="graph config")
    meta = {'collection': 'tables', 'indexes': ['name', 'columns']}
