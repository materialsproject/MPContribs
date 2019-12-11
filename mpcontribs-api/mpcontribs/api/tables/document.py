from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import LazyReferenceField, StringField, ListField, DictField, BooleanField
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions


class Tables(Document):
    project = LazyReferenceField(
        Projects, passthrough=True, reverse_delete_rule=CASCADE,
        help_text="project this table belongs to"
    )
    contribution = LazyReferenceField(
        Contributions, passthrough=True, reverse_delete_rule=CASCADE,
        help_text="contribution this table belongs to"
    )
    is_public = BooleanField(required=True, default=False, help_text='public/private table')
    name = StringField(required=True, help_text="table name")
    columns = ListField(StringField(), required=True, help_text="column names")
    data = ListField(ListField(StringField()), required=True, help_text="table rows")
    config = DictField(help_text="graph config")
    meta = {'collection': 'tables', 'indexes': [
        'project', 'contribution', 'is_public', 'name', 'columns',
        {'fields': ('project', 'contribution')},
        {'fields': ('project', 'contribution', 'name'), 'unique': True}
    ]}
