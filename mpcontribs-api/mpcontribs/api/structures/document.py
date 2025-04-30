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
        structure = Structure.from_dict(d)
        writer = None

        for symprec_log in range(-10, 0, 3):
            try:
                writer = CifWriter(structure, symprec=10**symprec_log)
                break
            except SymmetryUndeterminedError:
                continue

        if not writer:
            # save CIF string without symmetry information
            writer = CifWriter(structure)

        document.cif = writer.__str__()


signals.pre_save_post_validation.connect(
    Structures.pre_save_post_validation, sender=Structures
)
