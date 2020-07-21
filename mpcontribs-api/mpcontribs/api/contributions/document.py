# -*- coding: utf-8 -*-
import os
from math import isnan
from datetime import datetime
from nbformat import v4 as nbf
from copy import deepcopy
from flask import current_app
from flask_mongoengine import Document
from mongoengine import CASCADE, signals
from mongoengine.queryset import DoesNotExist
from mongoengine.fields import StringField, BooleanField, DictField
from mongoengine.fields import LazyReferenceField, ReferenceField
from mongoengine.fields import DateTimeField, ListField
from marshmallow.utils import get_value, _Missing
from boltons.iterutils import remap
from decimal import Decimal
from pint.errors import DimensionalityError

from mpcontribs.api import enter, valid_dict, Q_, max_dgts, quantity_keys, delimiter
from mpcontribs.api.notebooks import connect_kernel, execute

seed_nb = nbf.new_notebook()
seed_nb["cells"] = [nbf.new_code_cell("from mpcontribs.client import Client")]
MPCONTRIBS_API_HOST = os.environ.get("MPCONTRIBS_API_HOST", "localhost:5000")


def is_float(s):
    try:
        float(s)
    except ValueError:
        return False
    return True


def get_min_max(sender, path):
    # NOTE can't filter for project when using wildcard index data.$**
    # https://docs.mongodb.com/manual/core/index-wildcard/#wildcard-index-query-sort-support
    field = f"{path}{delimiter}value"
    key = f"{field}__type".replace(delimiter, "__")
    q = {key: "number"}  # NOTE need a query to trigger wildcard IXSCAN
    qs = sender.objects(**q).only(field).order_by(field)
    values = [get_value(doc, field) for doc in qs]
    values = [v for v in values if not isinstance(v, _Missing)]
    return (values[0], values[-1]) if len(values) else (None, None)


class Contributions(Document):
    project = LazyReferenceField(
        "Projects", required=True, passthrough=True, reverse_delete_rule=CASCADE
    )
    identifier = StringField(required=True, help_text="material/composition identifier")
    formula = StringField(help_text="formula (set dynamically)")
    is_public = BooleanField(
        required=True, default=False, help_text="public/private contribution"
    )
    last_modified = DateTimeField(
        required=True, default=datetime.utcnow, help_text="time of last modification"
    )
    data = DictField(
        default={}, validation=valid_dict, help_text="simple free-form data"
    )
    # TODO in flask-mongorest: also get all ReferenceFields when download requested
    structures = ListField(ReferenceField("Structures"), default=list)
    tables = ListField(ReferenceField("Tables"), default=list)
    notebook = ReferenceField("Notebooks")
    meta = {
        "collection": "contributions",
        "indexes": [
            "project",
            "identifier",
            "formula",
            "is_public",
            "last_modified",
            {"fields": [(r"data.$**", 1)]},
        ],
    }

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

        # set formula field
        if hasattr(document, "formula"):
            formulae = current_app.config["FORMULAE"]
            document.formula = formulae.get(document.identifier, document.identifier)

        # project is LazyReferenceField
        project = document.project.fetch()

        # run data through Pint Quantities and save as dicts
        # TODO set maximum number of columns
        def make_quantities(path, key, value):
            if key not in quantity_keys and isinstance(value, (str, int, float)):
                str_value = str(value)
                words = str_value.split()
                try_quantity = bool(len(words) == 2 and is_float(words[0]))

                if try_quantity or is_float(value):
                    field = delimiter.join(["data"] + list(path) + [key])
                    q = Q_(str_value).to_compact()

                    if not q.check(0):
                        q.ito_reduced_units()

                    # ensure that the same units are used across contributions
                    try:
                        column = project.columns.get(path=field)
                        if column.unit != str(q.units):
                            q.ito(column.unit)
                    except DoesNotExist:
                        pass  # column doesn't exist yet (generated in post_save)
                    except DimensionalityError:
                        raise ValueError(
                            f"Can't convert [{q.units}] to [{column.unit}]!"
                        )

                    v = Decimal(str(q.magnitude))
                    vt = v.as_tuple()

                    if vt.exponent < 0:
                        dgts = len(vt.digits)
                        dgts = max_dgts if dgts > max_dgts else dgts
                        v = f"{v:.{dgts}g}"

                        if try_quantity:
                            q = Q_(f"{v} {q.units}")

                    value = {
                        "display": str(q),
                        "value": q.magnitude,
                        "unit": str(q.units),
                    }

            return key, value

        document.data = remap(document.data, visit=make_quantities, enter=enter)

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

        # avoid circular imports
        from mpcontribs.api.projects.document import Column
        from mpcontribs.api.notebooks.document import Notebooks

        # project is LazyReferenceField
        project = document.project.fetch()

        # set columns field for project
        def update_columns(path, key, value):
            path = delimiter.join(["data"] + list(path) + [key])
            is_quantity = isinstance(value, dict) and quantity_keys == set(value.keys())
            is_text = bool(
                not is_quantity and isinstance(value, str) and key not in quantity_keys
            )
            if is_quantity or is_text:
                try:
                    column = project.columns.get(path=path)
                    if is_quantity:
                        column.min, column.max = get_min_max(sender, path)

                except DoesNotExist:
                    column = Column(path=path)
                    if is_quantity:
                        column.unit = value["unit"]
                        column.min = column.max = value["value"]

                    project.columns.append(column)

            return True

        # run update_columns over document data
        remap(document.data, visit=update_columns, enter=enter)
        project.save()

        # add/remove columns for other components
        for path in ["structures", "tables"]:
            try:
                project.columns.get(path=path)
            except DoesNotExist:
                if getattr(document, path):
                    project.update(push__columns=Column(path=path))

        # generate notebook for this contribution
        if document.notebook is not None:
            document.notebook.delete()

        cells = [
            nbf.new_code_cell(
                "client = Client(\n"
                '\theaders={"X-Consumer-Groups": "admin"},\n'
                f'\thost="{MPCONTRIBS_API_HOST}"\n'
                ")"
            ),
            nbf.new_code_cell(f'client.get_contribution("{document.id}").pretty()'),
        ]

        if document.tables:
            cells.append(nbf.new_markdown_cell("## Tables"))
            for table in document.tables:
                cells.append(
                    nbf.new_code_cell(f'client.get_table("{table.id}").plot()')
                )

        if document.structures:
            cells.append(nbf.new_markdown_cell("## Structures"))
            for structure in document.structures:
                cells.append(
                    nbf.new_code_cell(f'client.get_structure("{structure.id}")')
                )

        ws = connect_kernel()
        for cell in cells:
            if cell["cell_type"] == "code":
                cell["outputs"] = execute(ws, str(document.id), cell["source"])

        ws.close()
        cells[0] = nbf.new_code_cell("client = Client('<your-api-key-here>')")
        doc = deepcopy(seed_nb)
        doc["cells"] += cells
        document.notebook = Notebooks(**doc).save()
        document.last_modified = datetime.utcnow()
        document.save(signal_kwargs={"skip": True})

    @classmethod
    def pre_delete(cls, sender, document, **kwargs):
        document.reload()

        # remove reference documents
        if document.notebook is not None:
            document.notebook.delete()

        for structure in document.structures:
            structure.delete()

        for table in document.tables:
            table.delete()

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        # reset columns field for project
        project = document.project.fetch()

        for column in list(project.columns):
            if not isnan(column.min) and not isnan(column.max):
                column.min, column.max = get_min_max(sender, column.path)
                if isnan(column.min) and isnan(column.max):
                    # just deleted last contribution with this column
                    project.update(pull__columns__path=column.path)
            else:
                # use wildcard index if available -> single field query
                field = column.path.replace(delimiter, "__") + "__type"
                qs = sender.objects(**{field: "string"}).only(column.path)

                if qs.count() < 1:
                    project.update(pull__columns__path=column.path)


signals.pre_save_post_validation.connect(
    Contributions.pre_save_post_validation, sender=Contributions
)
signals.post_save.connect(Contributions.post_save, sender=Contributions)
signals.pre_delete.connect(Contributions.pre_delete, sender=Contributions)
signals.post_delete.connect(Contributions.post_delete, sender=Contributions)
