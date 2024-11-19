# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import six
import codecs
import os
from abc import ABCMeta
from tempfile import gettempdir
from mpcontribs.io.core import replacements, mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict, get_composition_from_string
from mpcontribs.io.core.components.hdata import HierarchicalData
from mpcontribs.io.core.components.tdata import TabularData, Table
from mpcontribs.io.core.components.gdata import GraphicalData
from mpcontribs.io.core.components.sdata import StructuralData

default_mpfile_path = os.path.join(gettempdir(), "mpfile.txt")


class MPFileCore(six.with_metaclass(ABCMeta, object)):
    """Abstract Base Class for representing a MP Contribution File"""

    def __init__(self, data=RecursiveDict()):
        if isinstance(data, dict):
            self.document = RecursiveDict(data)
        else:
            raise ValueError("Need dict (or inherited class) to init MPFile.")
        self.document.rec_update()  # convert (most) OrderedDict's to RecursiveDict's
        self.unique_mp_cat_ids = True
        self.max_contribs = 10

    def __getitem__(self, key):
        item = self.from_dict({key: self.document[key]})
        general = self.document.get(mp_level01_titles[0])
        if general:
            item.insert_general_section(self.from_dict({mp_level01_titles[0]: general}))
        return item

    @property
    def ids(self):
        return [k for k in self.document.keys() if k.lower() != mp_level01_titles[0]]

    @property
    def hdata(self):
        return HierarchicalData(self.document)

    @property
    def tdata(self):
        return TabularData(self.document)

    @property
    def gdata(self):
        return GraphicalData(self.document)

    @property
    def sdata(self):
        return StructuralData(self.document)

    @classmethod
    def from_file(cls, filename_or_file=default_mpfile_path.replace(".txt", "_in.txt")):
        """Reads a MPFile from a file.

        Args:
            filename_or_file (str or file): name of file or file containing contribution data.

        Returns:
            MPFile object.
        """
        f = (
            open(filename_or_file)
            if isinstance(filename_or_file, six.string_types)
            else filename_or_file
        )
        return cls.from_string(f.read())

    @classmethod
    def from_dict(cls, data=RecursiveDict()):
        return cls(data=data)

    @classmethod
    def from_contribution(cls, contrib):
        """construct MPFile from contribution (see rest.adapter.submit_contribution)"""
        if "identifier" not in contrib or "content" not in contrib:
            raise ValueError("Dict not in contribution-style format")
        recdict = RecursiveDict({contrib["identifier"]: contrib["content"]})
        return cls.from_dict(recdict)

    def write_file(
        self, filename=default_mpfile_path.replace(".txt", "_out.txt"), **kwargs
    ):
        """Writes MPFile to a file. The supported kwargs are the same as those
        for the MPFile.get_string method and are passed through directly."""
        with codecs.open(filename, encoding="utf-8", mode="w") as f:
            file_str = self.get_string(**kwargs) + "\n"
            f.write(file_str)
            print(
                "{} ({:.3f}MB) written".format(
                    filename, os.path.getsize(filename) / 1024.0 / 1024.0
                )
            )

    def get_number_of_lines(self, **kwargs):
        return len(self.get_string(**kwargs).split("\n"))

    def split(self):
        general_mpfile = (
            self.pop_first_section()
            if mp_level01_titles[0] in self.document.keys()
            else None
        )
        if not self.document:
            raise ValueError(
                "No contributions in MPFile! Either the file is"
                " empty or only contains shared (meta-)data not"
                " correlated to core identifier."
            )
        while True:
            try:
                mpfile_single = self.pop_first_section()
                mpid_orig = mpfile_single.ids[0]
                if "--" in mpid_orig:
                    mpid = mpid_orig.split("--")[0]
                    mpfile_single.document.rec_update(
                        nest_dict(mpfile_single.document.pop(mpid_orig), [mpid])
                    )
                if general_mpfile is not None:
                    mpfile_single.insert_general_section(general_mpfile)
                yield mpfile_single
            except KeyError:
                break

    def get_identifiers(self):
        """list of materials/composition identifiers as tuples w/ contribution IDs"""
        return [
            (k, self.document[k].get("cid", None))
            for k in self.document
            if k.lower() != mp_level01_titles[0]
        ]

    def pop_first_section(self):
        item = self.document.popitem(last=False)
        return self.from_dict(RecursiveDict([item]))

    def insert_general_section(self, general_mpfile):
        """insert general section from `general_mpfile` into this MPFile"""
        if general_mpfile is None:
            return
        general_title = mp_level01_titles[0]
        general_data = general_mpfile.document[general_title]
        root_key = list(self.document.keys())[0]
        for key, value in general_data.items():
            if key in self.document[root_key]:
                self.document.rec_update(nest_dict(value, [root_key, key]))
            else:
                self.document[root_key][key] = value
        for key in reversed(general_data.keys()):
            self.document[root_key].move_to_end(key, last=False)

    def get_unique_mp_cat_id(self, mp_cat_id):
        if not self.unique_mp_cat_ids or mp_cat_id in mp_level01_titles:
            return mp_cat_id
        mp_cat_id_idx = len([i for i in self.ids if i.startswith(mp_cat_id)])
        if mp_cat_id_idx == 0:
            return mp_cat_id
        return "{}--{}".format(mp_cat_id, mp_cat_id_idx)

    def concat(self, mpfile):
        """concatenate single-section MPFile with this MPFile"""
        try:
            if len(mpfile.document) > 1:
                raise ValueError(
                    "concatenation only possible with single section files"
                )
        except AttributeError:
            raise ValueError("Provide a MPFile to concatenate")
        mp_cat_id = list(mpfile.document.keys())[0]
        general_title = mp_level01_titles[0]
        if general_title in mpfile.document[mp_cat_id]:
            general_data = mpfile.document[mp_cat_id].pop(general_title)
            if general_title not in self.document:
                self.document.rec_update(nest_dict(general_data, [general_title]))
        self.document.rec_update(
            nest_dict(
                mpfile.document.pop(mp_cat_id), [self.get_unique_mp_cat_id(mp_cat_id)]
            )
        )

    def insert_top(self, mp_cat_id, key, value):
        """insert value for `mp_cat_id` as `key: <value>` at top"""
        self.document[mp_cat_id][key] = str(value)
        self.document[mp_cat_id].move_to_end(key, last=False)

    def add_data_table(self, identifier, dataframe, name, plot_options=None):
        """add a datatable to the root-level section

        Args:
            identifier (str): MP category ID (`mp_cat_id`)
            dataframe (pandas.DataFrame): tabular data as Pandas DataFrame
            name (str): table name, optional if only one table in section
            plot_options (dict): options for according plotly graph
        """
        # TODO: optional table name, required if multiple tables per root-level section
        name = "".join([replacements.get(c, c) for c in name])
        self.document.rec_update(
            nest_dict(Table(dataframe).to_dict(), [identifier, name])
        )
        self.document[identifier].insert_default_plot_options(
            dataframe, name, update_plot_options=plot_options
        )

    def add_hierarchical_data(self, dct, identifier=mp_level01_titles[0]):
        if len(self.ids) >= self.max_contribs:
            raise StopIteration("Reached max. number of contributions in MPFile")
        self.document.rec_update(nest_dict(RecursiveDict(dct), [identifier]))

    def add_structure(self, source, name=None, identifier=None, fmt=None):
        """add a structure to the mpfile"""
        from pymatgen.core import Structure
        from pymatgen.ext.matproj import MPRester

        if isinstance(source, Structure):
            structure = source
        elif isinstance(source, dict):
            structure = Structure.from_dict(source)
        elif os.path.exists(source):
            structure = Structure.from_file(source, sort=True)
        elif isinstance(source, six.string_types):
            if fmt is None:
                raise ValueError("Need fmt to get structure from string!")
            structure = Structure.from_str(source, fmt, sort=True)
        else:
            raise ValueError(source, "not supported!")

        if name is not None:
            if not isinstance(name, six.string_types):
                raise ValueError("structure name needs to be a string")
            elif "." in name:
                raise ValueError("structure name cannot contain dots (.)")

        mpr = MPRester()
        if not mpr.api_key:
            raise ValueError(
                "API key not set. Run `pmg config --add PMG_MAPI_KEY <USER_API_KEY>`."
            )
        matched_mpids = mpr.find_structure(structure)
        formula = get_composition_from_string(structure.composition.formula)
        if not matched_mpids:
            if identifier is None:
                identifier = formula
                print(
                    "Structure not found in MP! Please submit via MPComplete to "
                    "obtain mp-id or manually choose an anchor mp-id! Continuing "
                    "with {} as identifier!".format(identifier)
                )
            else:
                print(
                    "Structure not found in MP! Forcing {} as identifier!".format(
                        identifier
                    )
                )
        elif identifier is None:
            identifier = matched_mpids[0]
            if len(matched_mpids) > 1:
                print("Multiple matching structures found in MP. Using", identifier)
        elif identifier not in matched_mpids:
            msg = "Structure does not match {} but instead {}!".format(
                identifier, matched_mpids
            )
            raise ValueError(msg)

        idx = len(self.document.get(identifier, {}).get(mp_level01_titles[3], {}))
        sub_key = formula if name is None else name
        if sub_key in self.document.get(identifier, {}).get(mp_level01_titles[3], {}):
            sub_key += "_{}".format(idx)
        self.document.rec_update(
            nest_dict(structure.as_dict(), [identifier, mp_level01_titles[3], sub_key])
        )
        return identifier

    def __repr__(self):
        return self.get_string(df_head_only=True)

    def __str__(self):
        return self.get_string(df_head_only=True)

    def _ipython_display_(self):
        from IPython.display import display_html

        display_html(self.hdata)
        display_html(self.tdata)
        display_html(self.gdata)
        display_html(self.sdata)

    # ----------------------------
    # Override these in subclasses
    # ----------------------------

    @staticmethod
    def from_string(data):
        """Reads a MPFile from a string containing contribution data."""
        return MPFileCore()

    def get_string(self, df_head_only=False):
        """Returns a string to be written as a file"""
        return repr(self.document)
