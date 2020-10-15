# -*- coding: utf-8 -*-
import json
from math import isnan
from hashlib import md5
from flask_mongoengine import DynamicDocument
from mongoengine import signals, EmbeddedDocument
from mongoengine.fields import StringField, ListField, IntField, EmbeddedDocumentField

from mpcontribs.api.contributions.document import truncate_digits, get_quantity


def format_cell(cell):
    if cell.count(" ") > 1:
        return cell

    q = get_quantity(cell)
    if not q:
        return cell

    q = truncate_digits(q)
    return str(q.value) if isnan(q.std_dev) else str(q)


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
    def pre_save_post_validation(cls, sender, document, **kwargs):
        from mpcontribs.api.tables.views import TablesResource

        # significant digits
        document.data = [[format_cell(cell) for cell in row] for row in document.data]

        # md5 and total_data_rows
        resource = TablesResource()
        d = resource.serialize(document, fields=["index", "columns", "data"])
        s = json.dumps(d, sort_keys=True).encode("utf-8")
        document.md5 = md5(s).hexdigest()
        document.total_data_rows = len(document.data)


signals.pre_save_post_validation.connect(Tables.pre_save_post_validation, sender=Tables)
