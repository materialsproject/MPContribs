# -*- coding: utf-8 -*-
import json

from hashlib import md5
from math import isnan
from datetime import datetime
from flask import current_app
from importlib import import_module
from fastnumbers import isfloat
from flask_mongoengine import DynamicDocument
from mongoengine import CASCADE, signals
from mongoengine.queryset import DoesNotExist
from mongoengine.fields import StringField, BooleanField, DictField
from mongoengine.fields import LazyReferenceField, ReferenceField
from mongoengine.fields import DateTimeField, ListField
from marshmallow.utils import get_value, _Missing
from boltons.iterutils import remap
from decimal import Decimal
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from uncertainties import ufloat_fromstr
from collections import defaultdict

from mpcontribs.api import enter, valid_dict, delimiter

quantity_keys = {"display", "value", "error", "unit"}
max_dgts = 6
ureg = UnitRegistry(
    autoconvert_offset_to_baseunit=True,
    preprocessors=[
        lambda s: s.replace("%%", " permille "),
        lambda s: s.replace("%", " percent "),
    ],
)
ureg.default_format = ",P~"

ureg.define(UnitDefinition("percent", "%", (), ScaleConverter(0.01)))
ureg.define(UnitDefinition("permille", "%%", (), ScaleConverter(0.001)))
ureg.define(UnitDefinition("ppm", "ppm", (), ScaleConverter(1e-6)))
ureg.define(UnitDefinition("ppb", "ppb", (), ScaleConverter(1e-9)))
ureg.define("atom = 1")
ureg.define("bohr_magneton = e * hbar / (2 * m_e) = µᵇ = µ_B = mu_B")
ureg.define("electron_mass = 9.1093837015e-31 kg = mₑ = m_e")

COMPONENTS = {
    "structures": ["lattice", "sites", "charge"],
    "tables": ["index", "columns", "data"],
    "attachments": ["mime", "content"],
}


def format_cell(cell):
    if cell.count(" ") > 1:
        return cell

    q = get_quantity(cell)
    if not q:
        return cell

    q = truncate_digits(q)
    return str(q.value) if isnan(q.std_dev) else str(q)


def new_error_units(measurement, quantity):
    if quantity.units == measurement.value.units:
        return measurement

    error = measurement.error.to(quantity.units)
    return ureg.Measurement(quantity, error)


def get_quantity(s):
    # 5, 5 eV, 5+/-1 eV, 5(1) eV
    # set uncertainty to nan if not provided
    parts = s.split()
    parts += [None] * (2 - len(parts))
    if isfloat(parts[0]):
        parts[0] += "+/-nan"

    try:
        parts[0] = ufloat_fromstr(parts[0])
        return ureg.Measurement(*parts)
    except ValueError:
        return None


def truncate_digits(q):
    v = Decimal(str(q.nominal_value))
    vt = v.as_tuple()

    if vt.exponent >= 0:
        return q

    dgts = len(vt.digits)
    dgts = max_dgts if dgts > max_dgts else dgts
    s = f"{v:.{dgts}g}"
    if not isnan(q.std_dev):
        s += f"+/-{q.std_dev:.{dgts}g}"

    if q.units:
        s += f" {q.units}"

    return get_quantity(s)


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


def get_resource(component):
    klass = component.capitalize()
    vmodule = import_module(f"mpcontribs.api.{component}.views")
    Resource = getattr(vmodule, f"{klass}Resource")
    return Resource()


def get_md5(resource, obj, fields):
    d = resource.serialize(obj, fields=fields)
    s = json.dumps(d, sort_keys=True).encode("utf-8")
    return md5(s).hexdigest()


class Contributions(DynamicDocument):
    project = LazyReferenceField(
        "Projects", required=True, passthrough=True, reverse_delete_rule=CASCADE
    )
    identifier = StringField(required=True, help_text="material/composition identifier")
    formula = StringField(help_text="formula (set dynamically if not provided)")
    is_public = BooleanField(
        required=True, default=False, help_text="public/private contribution"
    )
    last_modified = DateTimeField(
        required=True, default=datetime.utcnow, help_text="time of last modification"
    )
    data = DictField(
        default={}, validation=valid_dict, help_text="simple free-form data"
    )
    structures = ListField(
        ReferenceField("Structures", null=True), default=list, max_length=10
    )
    tables = ListField(
        ReferenceField("Tables", null=True), default=list, max_length=10
    )
    attachments = ListField(
        ReferenceField("Attachments", null=True), default=list, max_length=10
    )
    notebook = LazyReferenceField("Notebooks", passthrough=True)
    meta = {
        "collection": "contributions",
        "indexes": [
            "project",
            "identifier",
            "formula",
            "is_public",
            "last_modified",
            {"fields": [(r"data.$**", 1)]},
            "notebook",
        ]
        + list(COMPONENTS.keys()),
    }

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        # replace existing components with according ObjectIds
        for component, fields in COMPONENTS.items():
            lst = document._data.get(component)
            if lst and lst[0].id is None:  # id is None for incoming POST
                resource = get_resource(component)
                for i, o in enumerate(lst):
                    digest = get_md5(resource, o, fields)
                    obj = resource.document.objects(md5=digest).only("id").first()
                    if obj:
                        lst[i] = obj.to_dbref()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

        # set formula field
        if hasattr(document, "formula") and not document.formula:
            formulae = current_app.config["FORMULAE"]
            document.formula = formulae.get(document.identifier, document.identifier)

        # project is LazyReferenceField
        project = document.project.fetch()

        # run data through Pint Quantities and save as dicts
        def make_quantities(path, key, value):
            if key in quantity_keys or not isinstance(value, (str, int, float)):
                return key, value

            str_value = str(value)
            if str_value.count(" ") > 1:
                return key, value

            q = get_quantity(str_value)
            if not q:
                return key, value

            # silently ignore "nan"
            if isnan(q.nominal_value):
                return False

            # try compact representation
            qq = q.value.to_compact()
            q = new_error_units(q, qq)

            # reduce dimensionality if possible
            if not q.check(0):
                qq = q.value.to_reduced_units()
                q = new_error_units(q, qq)

            # ensure that the same units are used across contributions
            field = delimiter.join(["data"] + list(path) + [key])
            try:
                column = project.columns.get(path=field)
                if column.unit != str(q.value.units):
                    qq = q.value.to(column.unit)
                    q = new_error_units(q, qq)
            except DoesNotExist:
                pass  # column doesn't exist yet (generated in post_save)
            except DimensionalityError:
                raise ValueError(
                    f"Can't convert [{q.units}] to [{column.unit}] for {field}!"
                )

            # significant digits
            q = truncate_digits(q)

            # return new value dict
            display = str(q.value) if isnan(q.std_dev) else str(q)
            value = {
                "display": display,
                "value": q.nominal_value,
                "error": q.std_dev,
                "unit": str(q.units),
            }
            return key, value

        document.data = remap(document.data, visit=make_quantities, enter=enter)
        document.last_modified = datetime.utcnow()

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

        # project is LazyReferenceField
        project = document.project.fetch()

        # set columns field for project
        def update_columns(path, key, value):
            path = delimiter.join(["data"] + list(path) + [key])
            is_quantity = isinstance(value, dict) and quantity_keys.issubset(
                value.keys()
            )
            is_text = bool(
                not is_quantity and isinstance(value, str) and key not in quantity_keys
            )
            if is_quantity or is_text:
                project.reload("columns")
                try:
                    column = project.columns.get(path=path)
                    if is_quantity:
                        v = value["value"]
                        if isnan(column.max) or v > column.max:
                            column.max = v
                        if isnan(column.min) or v < column.min:
                            column.min = v

                except DoesNotExist:
                    column = {"path": path}
                    if is_quantity:
                        column["unit"] = value["unit"]
                        column["min"] = column["max"] = value["value"]

                    project.columns.create(**column)

                project.save().reload("columns")
                ncolumns = len(project.columns)
                if ncolumns > 50:
                    raise ValueError("Reached maximum number of columns (50)!")

            return True

        # run update_columns over document data
        remap(document.data, visit=update_columns, enter=enter)

        # add/remove columns for other components
        for path in COMPONENTS.keys():
            try:
                project.columns.get(path=path)
            except DoesNotExist:
                if getattr(document, path):
                    project.columns.create(path=path)
                    project.save().reload("columns")

    @classmethod
    def pre_delete(cls, sender, document, **kwargs):
        args = ["notebook"] + list(COMPONENTS.keys())
        document.reload(*args)
        deleted = defaultdict(list)

        for component in COMPONENTS.keys():
            # check if other contributions exist before deletion!
            for idx, obj in enumerate(getattr(document, component)):
                q = {component: obj.id}
                if sender.objects(**q).count() < 2:
                    obj.delete()
                    deleted[component].append(idx)

        # remove reference documents
        if document.notebook is not None:
            from mpcontribs.api.notebooks.document import Notebooks

            nid = document.notebook.id
            nb = Notebooks.objects(id=nid).first()
            nb.delete(signal_kwargs=deleted)


    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        if kwargs.get("skip"):
            return

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

                if qs.count() < 1 or qs.filter(project__name=project.name).count() < 1:
                    project.update(pull__columns__path=column.path)


signals.post_init.connect(Contributions.post_init, sender=Contributions)
signals.pre_save_post_validation.connect(
    Contributions.pre_save_post_validation, sender=Contributions
)
signals.post_save.connect(Contributions.post_save, sender=Contributions)
signals.pre_delete.connect(Contributions.pre_delete, sender=Contributions)
signals.post_delete.connect(Contributions.post_delete, sender=Contributions)
