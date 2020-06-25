# -*- coding: utf-8 -*-
from flask_mongoengine import DynamicDocument
from mongoengine import CASCADE, signals
from mongoengine.fields import (
    LazyReferenceField,
    StringField,
    ListField,
    DictField,
    BooleanField,
)
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks


class Tables(DynamicDocument):
    contribution = LazyReferenceField(
        Contributions,
        passthrough=True,
        reverse_delete_rule=CASCADE,
        required=True,
        help_text="contribution this table belongs to",
    )
    is_public = BooleanField(
        required=True, default=False, help_text="public/private table"
    )
    name = StringField(required=True, help_text="table name")
    columns = ListField(StringField(), required=True, help_text="column names")
    data = ListField(ListField(StringField()), required=True, help_text="table rows")
    config = DictField(help_text="graph config")
    meta = {
        "collection": "tables",
        "indexes": [
            "contribution",
            "is_public",
            "name",
            "columns",
            {"fields": ("contribution", "name"), "unique": True},
        ],
    }

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        set_root_keys = set(k.split(".", 1)[0] for k in document._delta()[0].keys())
        nbs = Notebooks.objects(pk=document.contribution.id)
        if not set_root_keys or set_root_keys == {"is_public"}:
            nbs.update(set__is_public=document.is_public)
        else:
            nbs.delete()
            if "data" in set_root_keys:
                document.update(unset__total_data_rows=True)


signals.post_save.connect(Tables.post_save, sender=Tables)
