from flask_mongoengine import Document
from mongoengine import CASCADE, signals
from mongoengine.fields import StringField, LazyReferenceField, BooleanField
from mongoengine.fields import FloatField, IntField, ListField, DictField
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks


class Structures(Document):
    contribution = LazyReferenceField(
        Contributions, passthrough=True, reverse_delete_rule=CASCADE,
        required=True, help_text="contribution this structure belongs to"
    )
    is_public = BooleanField(required=True, default=False, help_text='public/private structure')
    name = StringField(required=True, help_text="table name")
    lattice = DictField(required=True, help_text="lattice")
    sites = ListField(DictField(), required=True, help_text="sites")
    charge = FloatField(null=True, help_text='charge')
    klass = StringField(help_text="@class")
    module = StringField(help_text="@module")
    meta = {'collection': 'structures', 'indexes': [
        'contribution', 'is_public', 'name',
        {'fields': ('contribution', 'name'), 'unique': True}
    ]}

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        Notebooks.objects(pk=document.contribution.id).delete()


signals.post_save.connect(Structures.post_save, sender=Structures)
