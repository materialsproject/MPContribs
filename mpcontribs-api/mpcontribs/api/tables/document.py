# -*- coding: utf-8 -*-
import json
from math import isnan
from hashlib import md5
from flask_mongoengine import DynamicDocument
from mongoengine import signals, EmbeddedDocument
from mongoengine.fields import StringField, ListField, IntField, EmbeddedDocumentField

from mpcontribs.api.contributions.document import format_cell, get_resource, get_md5, COMPONENTS


class Labels(EmbeddedDocument):
    index = StringField(help_text="index name / x-axis label")
    value = StringField(help_text="columns name / y-axis label")
    variable = StringField(help_text="legend name")


class Attributes(EmbeddedDocument):
    title = StringField(help_text="title")
    labels = EmbeddedDocumentField(Labels)


class Tables(DynamicDocument):
    name = StringField(required=True, help_text="name / title")
    attrs = EmbeddedDocumentField(Attributes)
    index = ListField(StringField(), required=True, help_text="index column")
    columns = ListField(StringField(), required=True, help_text="column names/headers")
    data = ListField(ListField(StringField()), required=True, help_text="table rows")
    md5 = StringField(regex=r"^[a-z0-9]{32}$", unique=True, help_text="md5 sum")
    total_data_rows = IntField(help_text="total number of rows")
    meta = {"collection": "tables", "indexes": ["name", "columns", "md5"]}

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        document.data = [[format_cell(cell) for cell in row] for row in document.data]

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        # significant digits, md5 and total_data_rows
        resource = get_resource("tables")
        document.md5 = get_md5(resource, document, COMPONENTS["tables"])
        document.total_data_rows = len(document.data)


signals.post_init.connect(Tables.post_init, sender=Tables)
signals.pre_save_post_validation.connect(Tables.pre_save_post_validation, sender=Tables)
