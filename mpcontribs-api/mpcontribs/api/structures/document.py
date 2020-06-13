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
        set_root_keys = set(k.split(".", 1)[0] for k in document._delta()[0].keys())
        cid = document.contribution.id
        nbs = Notebooks.objects(pk=cid)
        if not set_root_keys or set_root_keys == {"is_public"}:
            nbs.update(set__is_public=document.is_public)
        else:
            nbs.delete()
            document.update(unset__cif=True)
            Contributions.objects(pk=cid).update(unset__structures=True)


signals.post_save.connect(Structures.post_save, sender=Structures)
