# -*- coding: utf-8 -*-
import json
import itertools

from hashlib import md5
from math import isnan
from datetime import datetime
from flask import current_app
from atlasq import AtlasManager, AtlasQ
from itertools import permutations
from importlib import import_module
from fastnumbers import isfloat
from mongoengine import CASCADE, signals, DynamicDocument
from mongoengine.queryset.manager import queryset_manager
from mongoengine.fields import StringField, BooleanField, DictField
from mongoengine.fields import LazyReferenceField, ReferenceField
from mongoengine.fields import DateTimeField, ListField
from boltons.iterutils import remap
from decimal import Decimal
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from uncertainties import ufloat_fromstr
from pymatgen.core import Composition, Element

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
ureg.default_format = "~,P"

ureg.define(UnitDefinition("percent", "%", (), ScaleConverter(0.01)))
ureg.define(UnitDefinition("permille", "%%", (), ScaleConverter(0.001)))
ureg.define(UnitDefinition("ppm", "ppm", (), ScaleConverter(1e-6)))
ureg.define(UnitDefinition("ppb", "ppb", (), ScaleConverter(1e-9)))
ureg.define("atom = 1")
ureg.define("bohr_magneton = e * hbar / (2 * m_e) = µᵇ = µ_B = mu_B")
ureg.define("electron_mass = 9.1093837015e-31 kg = mₑ = m_e")
ureg.define("sccm = cm³/min")

COMPONENTS = {
    "structures": ["lattice", "sites", "charge"],
    "tables": ["index", "columns", "data"],
    "attachments": ["mime", "content"],
}


def grouper(n, iterable):
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk


def format_cell(cell):
    cell = cell.strip()
    if not cell or cell.count(" ") > 1:
        return cell

    q = get_quantity(cell)
    if not q or isnan(q.nominal_value):
        return cell

    q = truncate_digits(q)
    try:
        return str(q.nominal_value) if isnan(q.std_dev) else str(q)
    except Exception:
        return cell


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
    if isnan(q.nominal_value):
        return q

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
        required=True, default=True, help_text="public/private contribution"
    )
    last_modified = DateTimeField(
        required=True, default=datetime.utcnow, help_text="time of last modification"
    )
    needs_build = BooleanField(default=True, help_text="needs notebook build?")
    data = DictField(
        default=dict,
        validation=valid_dict,
        pullout_key="display",
        help_text="simple free-form data",
    )
    structures = ListField(
        ReferenceField("Structures", null=True), default=list, max_length=10
    )
    tables = ListField(ReferenceField("Tables", null=True), default=list, max_length=10)
    attachments = ListField(
        ReferenceField("Attachments", null=True), default=list, max_length=10
    )
    notebook = ReferenceField("Notebooks")
    atlas = AtlasManager("formula_autocomplete")
    meta = {
        "collection": "contributions",
        "indexes": [
            "project",
            "identifier",
            "formula",
            "is_public",
            "last_modified",
            "needs_build",
            "notebook",
            {"fields": [(r"data.$**", 1)]},
            # can only use wildcardProjection option with wildcard index on all document fields
            {"fields": [(r"$**", 1)], "wildcardProjection": {"project": 1}},
        ]
        + list(COMPONENTS.keys()),
    }

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.no_dereference().only(
            "project",
            "identifier",
            "formula",
            "is_public",
            "last_modified",
            "needs_build",
        )

    @classmethod
    def atlas_filter(cls, term):
        try:
            comp = Composition(term)
        except Exception:
            raise ValueError(f"{term} is not a valid composition")

        try:
            for element in comp.elements:
                Element(element)
        except Exception:
            raise ValueError(f"{element} not a valid element")

        ind_str = []

        if len(comp) == 1:
            d = comp.get_integer_formula_and_factor()
            ind_str.append(d[0] + str(int(d[1])) if d[1] != 1 else d[0])
        else:
            for i, j in comp.reduced_composition.items():
                ind_str.append(i.name + str(int(j)) if j != 1 else i.name)

        final_terms = ["".join(entry) for entry in permutations(ind_str)]
        return AtlasQ(formula=final_terms[0])  # TODO formula__in=final_terms

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        # replace existing components with according ObjectIds
        for component, fields in COMPONENTS.items():
            lst = document._data.get(component)
            if lst and lst[0].id is None:  # id is None for incoming POST
                resource = get_resource(component)
                for i, o in enumerate(lst):
                    digest = get_md5(resource, o, fields)
                    objs = resource.document.objects(md5=digest)
                    exclude = list(resource.document._fields.keys())
                    obj = objs.exclude(*exclude).only("id").first()
                    if obj:
                        lst[i] = obj.to_dbref()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        # set formula field
        if hasattr(document, "formula") and not document.formula:
            formulae = current_app.config["FORMULAE"]
            document.formula = formulae.get(document.identifier, document.identifier)

        # project is LazyReferenceField & load columns due to custom queryset manager
        project = document.project.fetch().reload("columns")
        columns = {col.path: col for col in project.columns}

        # run data through Pint Quantities and save as dicts
        def make_quantities(path, key, value):
            key = key.strip()
            if key in quantity_keys or not isinstance(value, (str, int, float)):
                return key, value

            # can't be a quantity if contains 2+ spaces
            str_value = str(value).strip()
            if str_value.count(" ") > 1:
                return key, value

            # don't parse if column.unit indicates string type
            field = delimiter.join(["data"] + list(path) + [key])
            if field in columns:
                if columns[field].unit == "NaN":
                    return key, str_value

            # parse as quantity
            q = get_quantity(str_value)
            if not q._magnitude:
                return key, value

            # silently ignore "nan"
            if isnan(q.nominal_value):
                return False

            # ensure that the same units are used across contributions
            if field in columns:
                column = columns[field]
                if column.unit != str(q.value.units):
                    try:
                        qq = q.value.to(column.unit)
                        q = new_error_units(q, qq)
                    except DimensionalityError:
                        raise ValueError(
                            f"Can't convert [{q.units}] to [{column.unit}] for {field}!"
                        )
            else:
                # try compact representation
                qq = q.value.to_compact()
                q = new_error_units(q, qq)

                # reduce dimensionality if possible
                if not q.check(0):
                    qq = q.value.to_reduced_units()
                    q = new_error_units(q, qq)

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
        document.needs_build = True

    @classmethod
    def pre_delete(cls, sender, document, **kwargs):
        args = list(COMPONENTS.keys())
        document.reload(*args)

        for component in COMPONENTS.keys():
            # check if other contributions exist before deletion!
            for idx, obj in enumerate(getattr(document, component)):
                q = {component: obj.id}
                if sender.objects(**q).count() < 2:
                    obj.delete()


signals.post_init.connect(Contributions.post_init, sender=Contributions)
signals.pre_save_post_validation.connect(
    Contributions.pre_save_post_validation, sender=Contributions
)
signals.pre_delete.connect(Contributions.pre_delete, sender=Contributions)
