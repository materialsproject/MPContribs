# -*- coding: utf-8 -*-
from flask_mongoengine import DynamicDocument
from mongoengine import CASCADE, signals
from mongoengine.fields import StringField, LazyReferenceField, BooleanField
from mongoengine.fields import FloatField, ListField, DictField
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks


class Structures(DynamicDocument):
    contribution = LazyReferenceField(
        Contributions,
        passthrough=True,
        reverse_delete_rule=CASCADE,
        required=True,
        help_text="contribution this structure belongs to",
    )
    is_public = BooleanField(
        required=True, default=False, help_text="public/private structure"
    )
    name = StringField(required=True, help_text="structure name")
    label = StringField(required=True, help_text="structure label")
    lattice = DictField(required=True, help_text="lattice")
    sites = ListField(DictField(), required=True, help_text="sites")
    charge = FloatField(null=True, help_text="charge")
    klass = StringField(help_text="@class")
    module = StringField(help_text="@module")
    meta = {
        "collection": "structures",
        "indexes": ["contribution", "is_public", "label"],
    }

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        Notebooks.objects(pk=document.contribution.id).delete()
        document.update(unset__cif=True)


signals.post_save.connect(Structures.post_save, sender=Structures)
