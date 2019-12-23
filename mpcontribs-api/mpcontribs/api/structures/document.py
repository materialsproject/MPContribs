from flask_mongoengine import Document
from mongoengine import EmbeddedDocument, CASCADE, signals
from mongoengine.fields import StringField, LazyReferenceField, BooleanField, FloatField, IntField
from mongoengine.fields import ListField, EmbeddedDocumentField, EmbeddedDocumentListField
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks


class Lattice(EmbeddedDocument):
    a = FloatField(min_value=0, required=True, help_text='`a` lattice parameter')
    b = FloatField(min_value=0, required=True, help_text='`b` lattice parameter')
    c = FloatField(min_value=0, required=True, help_text='`c` lattice parameter')
    matrix = ListField(ListField(
        FloatField(min_value=0, required=True), max_length=3, required=True
    ), max_length=3, required=True, help_text='lattice')
    volume = FloatField(min_value=0, required=True, help_text='volume')
    alpha = FloatField(min_value=0, required=True, help_text='alpha')
    beta = FloatField(min_value=0, required=True, help_text='beta')
    gamma = FloatField(min_value=0, required=True, help_text='gamma')


class Specie(EmbeddedDocument):
    occu = IntField(min_value=0, required=True, help_text='occupancy')
    element = StringField(required=True, help_text='element')


class Properties(EmbeddedDocument):
    magmom = FloatField(min_value=0, help_text='magnetic moment')
    velocities = ListField(FloatField(min_value=0), max_length=3, help_text='velocities')


class Site(EmbeddedDocument):
    abc = ListField(
        FloatField(min_value=0, required=True),
        max_length=3, required=True, help_text='lattice'
    )
    xyz = ListField(
        FloatField(required=True), max_length=3, required=True, help_text='lattice'
    )
    label = StringField(required=True, help_text="site label")
    species = EmbeddedDocumentListField(Specie, required=True, help_text='species')
    properties = EmbeddedDocumentField(Properties, help_text="other properties")


class Structures(Document):
    contribution = LazyReferenceField(
        Contributions, passthrough=True, reverse_delete_rule=CASCADE,
        required=True, help_text="contribution this structure belongs to"
    )
    is_public = BooleanField(required=True, default=False, help_text='public/private structure')
    name = StringField(required=True, help_text="table name")
    lattice = EmbeddedDocumentField(Lattice, required=True, help_text="lattice")
    # TODO sites.0 and sites.label in _fields doesn't work yet -> deep_get?
    sites = EmbeddedDocumentListField(Site, required=True, help_text="sites")
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
