# -*- coding: utf-8 -*-
from fdict import fdict
from datetime import datetime
from nbformat import v4 as nbf
from copy import deepcopy
from flask import current_app
from flask_mongoengine import Document
from mongoengine import CASCADE, signals
from mongoengine.fields import StringField, BooleanField, DictField
from mongoengine.fields import (
    LazyReferenceField,
    DateTimeField,
    ListField,
    ReferenceField,
)

from mpcontribs.api import validate_data, delimiter, quantity_keys
from mpcontribs.api.notebooks import connect_kernel, execute
from mpcontribs.api.projects.document import Projects, Column
from mpcontribs.api.structures.document import Structures
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.notebooks.document import Notebooks

seed_nb = nbf.new_notebook()
seed_nb["cells"] = [nbf.new_code_cell("from mpcontribs.client import Client")]


class Contributions(Document):
    project = LazyReferenceField(
        Projects, required=True, passthrough=True, reverse_delete_rule=CASCADE
    )
    identifier = StringField(required=True, help_text="material/composition identifier")
    formula = StringField(help_text="formula (set dynamically)")
    is_public = BooleanField(
        required=True, default=False, help_text="public/private contribution"
    )
    data = DictField(default={}, help_text="simple free-form data")
    last_modified = DateTimeField(
        required=True, default=datetime.utcnow, help_text="time of last modification"
    )
    structures = ListField(ReferenceField(Structures), default=[])
    tables = ListField(ReferenceField(Tables), default=[])
    notebook = ReferenceField(Notebooks)
    meta = {
        "collection": "contributions",
        "indexes": ["project", "identifier", "formula", "is_public", "last_modified"],
    }

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.data = validate_data(
            document.data, sender=sender, project=document.project
        )
        if hasattr(document, "formula"):
            formulae = current_app.config["FORMULAE"]
            document.formula = formulae.get(document.identifier, document.identifier)

        document.last_modified = datetime.utcnow()

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        # set columns field for project
        flat_data = fdict(document.data, delimiter=delimiter)

        updated_columns = set()
        for column in document.project.columns:
            value = flat_data.get(column.name)
            if isinstance(value, dict) and value:
                column.unit = value.get("unit")
                val = value["value"]
                if not isinstance(val, str):
                    if val < column.min:
                        column.min = val
                    elif val > column.max:
                        column.max = val

                column.save()
                updated_columns.add(column.name)

        new_columns = set()
        for key in flat_data:
            key = key.strip()
            nodes = key.split(delimiter)
            is_quantity_key = bool(nodes[-1] in quantity_keys)
            name = delimiter.join(nodes[:-1]) if is_quantity_key else key
            if name not in updated_columns:
                new_columns.add(name)

        for name in new_columns:
            value = flat_data[name]
            column = {"name": name}
            if isinstance(value, dict):
                column["unit"] = value.get("unit")
                column["min"] = column["max"] = value["value"]

            document.project.columns.create(**column)

        for name in ["structures", "tables"]:
            if getattr(document, name):
                document.project.columns.create(name=name)

        # generate notebook for this contribution
        cells = [
            nbf.new_code_cell(
                'client = Client(headers={"X-Consumer-Groups": "admin"})'
            ),
            nbf.new_markdown_cell("## Project"),
            nbf.new_code_cell(f'client.get_project("{document.project.pk}").pretty()'),
            nbf.new_markdown_cell("## Contribution"),
            nbf.new_code_cell(f'client.get_contribution("{document.id}").pretty()'),
        ]

        if document.tables:
            cells.append(nbf.new_markdown_cell("## Tables"))
            for _, tables in document.tables.items():
                for table in tables:
                    tid = table["id"]
                    cells.append(nbf.new_code_cell(f'client.get_table("{tid}").plot()'))

        if document.structures:
            cells.append(nbf.new_markdown_cell("## Structures"))
            for _, structures in document.structures.items():
                for structure in structures:
                    sid = structure["id"]
                    cells.append(nbf.new_code_cell(f'client.get_structure("{sid}")'))

        doc = deepcopy(seed_nb)
        doc["cells"] += cells
        nb = Notebooks(**doc)
        # self.Schema().update(nb, doc)

        ws = connect_kernel()
        for idx, cell in enumerate(nb.cells):
            if cell["cell_type"] == "code":
                cell["outputs"] = execute(ws, document.id, cell["source"])

        ws.close()
        nb.cells[1] = nbf.new_code_cell("client = Client('<your-api-key-here>')")
        nb.save()  # calls Notebooks.clean()


signals.pre_save_post_validation.connect(
    Contributions.pre_save_post_validation, sender=Contributions
)
signals.post_save.connect(Contributions.post_save, sender=Contributions)
