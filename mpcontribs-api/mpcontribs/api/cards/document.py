# -*- coding: utf-8 -*-
from flask_mongoengine import Document
from mongoengine import CASCADE
from mongoengine.fields import LazyReferenceField, BooleanField, StringField
from mpcontribs.api.contributions.document import Contributions


class Cards(Document):
    contribution = LazyReferenceField(
        Contributions,
        passthrough=True,
        reverse_delete_rule=CASCADE,
        primary_key=True,
        help_text="contribution this table belongs to",
    )
    is_public = BooleanField(
        required=True, default=False, help_text="public or private card"
    )
    html = StringField(
        required=True, default="", help_text="embeddable html code (bootstrap)"
    )
    bulma = StringField(
        required=True, default="", help_text="embeddable html code (bulma)"
    )
    meta = {"collection": "cards", "indexes": ["is_public"]}
