# -*- coding: utf-8 -*-
import json
from hashlib import md5
from flask_mongoengine.documents import Document
from mongoengine import signals
from mongoengine.fields import StringField, FloatField, ListField, DictField
from mongoengine.queryset.manager import queryset_manager
from pymatgen.core import Structure
from pymatgen.io.cif import CifWriter
from pymatgen.symmetry.analyzer import SymmetryUndeterminedError


def make_cif(d: dict, symmetrize: bool = True) -> str:
    """Generate a CIF string from a serialized structure dict.

    Args:
        d: structure dict with at least "lattice" and "sites" (optionally "charge"),
            as produced by ``StructuresResource.serialize`` / ``Structure.as_dict``.
        symmetrize: if True, detect the crystallographic symmetry and write the CIF
            with space-group information (the pymatgen default). If False, write a
            P1 CIF that includes per-site properties as ``_atom_site_<prop>`` loop
            columns (e.g. ``_atom_site_charge``). These two modes are mutually
            exclusive: pymatgen only emits site properties on the un-symmetrized
            (``symprec=None``) code path, because symmetry reduction collapses
            equivalent sites.

    Returns:
        the CIF string.
    """
    structure = Structure.from_dict(d)

    if symmetrize:
        for symprec_log in range(-10, 0, 3):
            try:
                return CifWriter(structure, symprec=10**symprec_log).__str__()
            except SymmetryUndeterminedError:
                continue
        # fall back to a CIF without symmetry information
        return CifWriter(structure).__str__()

    try:
        return CifWriter(structure, write_site_properties=True).__str__()
    except (ValueError, TypeError):
        # non-numeric site property -> CifWriter can't format it; the canonical
        # values still live in ``sites[].properties``, so degrade gracefully.
        return CifWriter(structure).__str__()


class Structures(Document):
    name = StringField(required=True, help_text="name")
    lattice = DictField(required=True, help_text="lattice")
    sites = ListField(DictField(), required=True, help_text="sites")
    charge = FloatField(null=True, help_text="charge")
    md5 = StringField(regex=r"^[a-z0-9]{32}$", unique=True, help_text="md5 sum")
    cif = StringField(help_text="CIF string")
    meta = {"collection": "structures", "indexes": ["name", "md5"]}

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.only("name", "md5")

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        from mpcontribs.api.structures.views import StructuresResource

        resource = StructuresResource()
        d = resource.serialize(document, fields=["lattice", "sites", "charge"])
        s = json.dumps(d, sort_keys=True).encode("utf-8")
        document.md5 = md5(s).hexdigest()
        # store a symmetrized CIF as a default/backward-compatible fallback; API
        # reads regenerate on the fly from lattice/sites/charge (see
        # StructuresResource.cif), honoring the `symmetrize` query parameter.
        document.cif = make_cif(d, symmetrize=True)


signals.pre_save_post_validation.connect(
    Structures.pre_save_post_validation, sender=Structures
)
