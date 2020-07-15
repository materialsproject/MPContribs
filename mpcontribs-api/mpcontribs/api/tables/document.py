# -*- coding: utf-8 -*-
import json
from hashlib import md5
from flask_mongoengine import Document
from mongoengine import signals
from mongoengine.fields import StringField, ListField, IntField


class Tables(Document):
    name = StringField(required=True, help_text="name")
    columns = ListField(StringField(), required=True, help_text="column names")
    data = ListField(ListField(StringField()), required=True, help_text="table rows")
    md5 = StringField(regex=r"^[a-z0-9]{32}$", unique=True, help_text="md5 sum")
    total_data_rows = IntField(help_text="total number of rows")
    meta = {"collection": "tables", "indexes": ["name", "columns", "md5"]}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        from mpcontribs.api.tables.views import TablesResource

        resource = TablesResource()
        d = resource.serialize(document, fields=["columns", "data"])
        s = json.dumps(d, sort_keys=True).encode("utf-8")
        document.md5 = md5(s).hexdigest()
        document.total_data_rows = len(document.data)


signals.pre_save_post_validation.connect(Tables.pre_save_post_validation, sender=Tables)
