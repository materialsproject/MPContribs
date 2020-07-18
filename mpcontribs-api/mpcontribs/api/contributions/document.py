# -*- coding: utf-8 -*-
import operator
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
from marshmallow.utils import get_value
from boltons.iterutils import remap
from decimal import Decimal
from pint.errors import DimensionalityError

from mpcontribs.api import enter, valid_dict, Q_, max_dgts, quantity_keys, delimiter
from mpcontribs.api.notebooks import connect_kernel, execute

seed_nb = nbf.new_notebook()
seed_nb["cells"] = [nbf.new_code_cell("from mpcontribs.client import Client")]


def is_float(s):
    try:
        float(s)
    except ValueError:
        return False
    return True


def make_quantities(path, key, value):
    if key not in quantity_keys and isinstance(value, (str, int, float)):
        str_value = str(value)
        words = str_value.split()
        try_quantity = bool(len(words) == 2 and is_float(words[0]))

        if try_quantity or is_float(value):
            q = Q_(str_value).to_compact()

            if not q.check(0):
                q.ito_reduced_units()

            v = Decimal(str(q.magnitude))
            vt = v.as_tuple()

            if vt.exponent < 0:
                dgts = len(vt.digits)
                dgts = max_dgts if dgts > max_dgts else dgts
                v = f"{v:.{dgts}g}"

                if try_quantity:
                    q = Q_(f"{v} {q.units}")

            value = {"display": str(q), "value": q.magnitude, "unit": str(q.units)}

    return key, value


def set_min_max(sender, column, val=None):
    # NOTE val is set to incoming value if column (previous min/max) exists
    # can't filter for project when using wildcard index data.$**
    # https://docs.mongodb.com/manual/core/index-wildcard/#wildcard-index-query-sort-support
    field = f"{column.path}{delimiter}value"
    qs = sender.objects.only(field).order_by(field)
    ndocs = qs.count()

    if val is None:
        values = [get_value(doc, field) for doc in qs]

    for typ in ["min", "max"]:
        if val is None:
            if ndocs < 1:
                # just deleted last contribution with this column
                print("column delete?")
                break

            # just deleted a contribution -> reset column with new min/max
            val = values[0] if typ == "min" else values[-1]

        comp = getattr(operator, "lt" if typ == "min" else "gt")
        if ndocs == 1:
            # updating the only contribution
            setattr(column, typ, val)
        else:
            current = getattr(column, typ)
            if comp(val, current):
                print(f"set {column} {typ}: {val} {comp} {current}")
                setattr(column, typ, val)
                break


class Contributions(Document):
    project = LazyReferenceField(
        "Projects", required=True, passthrough=True, reverse_delete_rule=CASCADE
    )
    identifier = StringField(required=True, help_text="material/composition identifier")
    formula = StringField(help_text="formula (set dynamically)")
    is_public = BooleanField(
        required=True, default=False, help_text="public/private contribution"
    )
    data = DictField(
        default={}, validation=valid_dict, help_text="simple free-form data"
    )
    last_modified = DateTimeField(
        required=True, default=datetime.utcnow, help_text="time of last modification"
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

        from mpcontribs.api.projects.document import Column

        # set formula field
        if hasattr(document, "formula"):
            formulae = current_app.config["FORMULAE"]
            document.formula = formulae.get(document.identifier, document.identifier)

        # run data through Pint Quantities and save as dicts
        # TODO set maximum number of columns
        document.data = remap(document.data, visit=make_quantities, enter=enter)

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
                        q = Q_(value["display"])
                        # ensure that the same units are used across contributions
                        if column.unit != value["unit"]:
                            try:
                                q.ito(column.unit)
                            except DimensionalityError:
                                raise ValueError(
                                    f"Can't convert {q.units} to {column.unit}!"
                                )

                        set_min_max(sender, column, val=q.magnitude)

                except DoesNotExist:
                    column = Column(path=path)

                    if is_quantity:
                        column.unit = value["unit"]
                        column.min = column.max = value["value"]

                    project.columns.append(column)

            return True

        # run update_columns over document data
        remap(document.data, visit=update_columns, enter=enter)

        # add/remove columns for other components
        for path in ["structures", "tables"]:
            has_component = bool(getattr(document, path))
            try:
                column = project.columns.get(path=path)
                if not has_component:
                    project.update(pull__columns__path=path)
            except DoesNotExist:
                if has_component:
                    column = Column(path=path)
                    project.columns.append(column)

        # save columns in project and set last modified
        project.save()
        document.last_modified = datetime.utcnow()

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

        # generate notebook for this contribution
        from mpcontribs.api.notebooks.document import Notebooks

        if document.notebook is not None:
            document.notebook.delete()

        cells = [
            nbf.new_code_cell(
                'client = Client(headers={"X-Consumer-Groups": "admin"})'
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
        document.save(signal_kwargs={"skip": True})

    @classmethod
    def pre_delete(cls, sender, document, **kwargs):
        document.reload()

        # remove reference documents
        if document.notebook is not None:
            print("delete notebook", document.notebook.id)
            document.notebook.delete()

        for structure in document.structures:
            print("delete structure", structure.id)
            structure.delete()

        for table in document.tables:
            print("delete table", table.id)
            table.delete()

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        # reset columns field for project
        project = document.project.fetch()
        columns = list(project.columns)

        for idx, column in enumerate(columns):
            print("reset", column.path)
            if not isnan(column.min) and not isnan(column.max):
                set_min_max(sender, column)
            else:
                # use wildcard index if available -> single field query
                qs = sender.objects.only(column.path)
                if column.path in ["structures", "tables"]:
                    field = column.path.replace(delimiter, "__") + "__exists"
                    qs = qs.filter(**{field: True})

                if qs.count() < 1:
                    print(f"pop {column.path}")
                    project.columns.pop(idx)

        project.save()


signals.pre_save_post_validation.connect(
    Contributions.pre_save_post_validation, sender=Contributions
)
signals.post_save.connect(Contributions.post_save, sender=Contributions)
signals.pre_delete.connect(Contributions.pre_delete, sender=Contributions)
signals.post_delete.connect(Contributions.post_delete, sender=Contributions)
