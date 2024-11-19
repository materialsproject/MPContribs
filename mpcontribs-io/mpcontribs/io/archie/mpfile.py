# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import six
import textwrap

from archieml import loads
from pandas import MultiIndex

from mpcontribs.io.core import replacements, mp_level01_titles
from mpcontribs.io.core.mpfile import MPFileCore
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict, normalize_root_level
from mpcontribs.io.core.utils import read_csv, make_pair
from mpcontribs.io.core.components.tdata import Table


Quantity = None  # TODO


class MPFile(MPFileCore):
    """Object for representing a MP Contribution File in ArchieML format."""

    @staticmethod
    def from_string(data):
        # use archieml-python parse to import data
        rdct = RecursiveDict(loads(data))
        rdct.rec_update()

        # post-process internal representation of file contents
        for key in list(rdct.keys()):
            is_general, root_key = normalize_root_level(key)

            if is_general:
                # make part of shared (meta-)data, i.e. nest under `general` at
                # the beginning of the MPFile
                if mp_level01_titles[0] not in rdct:
                    rdct[mp_level01_titles[0]] = RecursiveDict()
                    rdct.move_to_end(mp_level01_titles[0], last=False)

            # normalize identifier key (pop & insert)
            # using rec_update since we're looping over all entries
            # also: support data in bare tables (marked-up only by
            #       root-level identifier) by nesting under 'data'
            value = rdct.pop(key)
            keys = [mp_level01_titles[0]] if is_general else []
            keys.append(root_key)
            if isinstance(value, list):
                keys.append("table")
            rdct.rec_update(nest_dict(value, keys))

            # reference to section to iterate or parse as CIF
            section = (
                rdct[mp_level01_titles[0]][root_key] if is_general else rdct[root_key]
            )

            # iterate to find CSV sections to parse
            # also parse propnet quantities
            if isinstance(section, dict):
                scope = []
                for k, v in section.iterate():
                    level, key = k
                    key = "".join([replacements.get(c, c) for c in key])
                    level_reduction = bool(level < len(scope))
                    if level_reduction:
                        del scope[level:]
                    if v is None:
                        scope.append(key)
                    elif isinstance(v, list) and isinstance(v[0], dict):
                        table = ""
                        for row_dct in v:
                            table = "\n".join([table, row_dct["value"]])
                        pd_obj = read_csv(table)
                        d = nest_dict(pd_obj.to_dict(), scope + [key])
                        section.rec_update(d, overwrite=True)
                        if not is_general and level == 0:
                            section.insert_default_plot_options(pd_obj, key)
                    elif (
                        Quantity is not None
                        and isinstance(v, six.string_types)
                        and " " in v
                    ):
                        quantity = Quantity.from_key_value(key, v)
                        d = nest_dict(
                            quantity.as_dict(), scope + [key]
                        )  # TODO quantity.symbol.name
                        section.rec_update(d, overwrite=True)

            # convert CIF strings into pymatgen structures
            if mp_level01_titles[3] in section:
                from pymatgen.io.cif import CifParser

                for name in section[mp_level01_titles[3]].keys():
                    cif = section[mp_level01_titles[3]].pop(name)
                    parser = CifParser.from_string(cif)
                    structure = parser.get_structures(primitive=False)[0]
                    section[mp_level01_titles[3]].rec_update(
                        nest_dict(structure.as_dict(), [name])
                    )

        return MPFile.from_dict(rdct)

    def get_string(self, df_head_only=False):
        from pymatgen.core import Structure

        lines, scope = [], []
        for key, value in self.document.iterate():
            if isinstance(value, Table):
                lines[-1] = lines[-1].replace("{", "[+").replace("}", "]")
                header = any([isinstance(col, str) for col in value])
                if isinstance(value.index, MultiIndex):
                    value.reset_index(inplace=True)
                if df_head_only:
                    value = value.head()
                csv_string = value.to_csv(
                    index=False, header=header, float_format="%g", encoding="utf-8"
                )[:-1]
                lines += csv_string.split("\n")
                if df_head_only:
                    lines.append("...")
            elif isinstance(value, Structure):
                from pymatgen.io.cif import CifWriter

                cif = CifWriter(value, symprec=1e-10).__str__()
                lines.append(
                    make_pair(
                        "".join([replacements.get(c, c) for c in key]), cif + ":end"
                    )
                )
            elif Quantity is not None and isinstance(value, Quantity):
                lines.append(make_pair(value.display_symbols[0], value.pretty_string()))
            else:
                level, key = key
                # truncate scope
                level_reduction = bool(level < len(scope))
                if level_reduction:
                    del scope[level:]
                # append scope
                if value is None:
                    scope.append("".join([replacements.get(c, c) for c in key]))
                # correct scope to omit internal 'general' section
                scope_corr = scope
                if scope[0] == mp_level01_titles[0]:
                    scope_corr = scope[1:]
                # insert scope line
                if (value is None and scope_corr) or (
                    value is not None and level_reduction
                ):
                    lines.append("\n{" + ".".join(scope_corr) + "}")
                # insert key-value line
                if value is not None:
                    val = str(value)
                    value_lines = (
                        [val] if val.startswith("http") else textwrap.wrap(val)
                    )
                    if len(value_lines) > 1:
                        value_lines = [""] + value_lines + [":end"]
                    lines.append(
                        make_pair(
                            "".join([replacements.get(c, c) for c in key]),
                            "\n".join(value_lines),
                        )
                    )
        return "\n".join(lines) + "\n"


MPFileCore.register(MPFile)
