# -*- coding: utf-8 -*-
import hashlib
import json
from collections import OrderedDict as _OrderedDict
from collections.abc import Mapping as _Mapping
from mpcontribs.io.core import replacements, mp_level01_titles

# try:
#    from propnet.core.quantity import Quantity
# except ImportError:
#    Quantity = None


class RecursiveDict(_OrderedDict):
    """extension of dict for internal representation of MPFile"""

    def rec_update(self, other=None, overwrite=False, replace_newlines=True):
        """https://gist.github.com/Xjs/114831"""
        # overwrite=False: don't overwrite existing unnested key
        if other is None:  # mode to force RecursiveDicts to be used
            other = self
            overwrite = True
        for key, value in other.items():
            if isinstance(key, str):
                key = "".join([replacements.get(c, c) for c in key])
            if key in self and isinstance(self[key], dict) and isinstance(value, dict):
                # ensure RecursiveDict and update key (w/o underscores)
                self[key] = RecursiveDict(self[key])
                replace_newlines = bool(key != mp_level01_titles[3])
                self[key].rec_update(
                    other=value, overwrite=overwrite, replace_newlines=replace_newlines
                )
            elif (key in self and overwrite) or key not in self:
                if isinstance(value, str) and replace_newlines:
                    self[key] = value.replace("\n", " ")
                else:
                    self[key] = value

    def iterate(self, nested_dict=None):
        """http://stackoverflow.com/questions/10756427/loop-through-all-nested-dictionary-values"""
        d = self if nested_dict is None else nested_dict
        if nested_dict is None:
            self.level = 0
        for key in list(d.keys()):
            value = d[key]
            if isinstance(value, _Mapping):
                if value.get("@class") == "Structure":
                    from pymatgen import Structure

                    yield key, Structure.from_dict(value)
                    continue
                yield (self.level, key), None
                if value.get("@class") == "Table":
                    from mpcontribs.io.core.components.tdata import Table

                    yield key, Table.from_dict(value)
                    continue
                # if Quantity is not None and value.get('@class') == 'Quantity':
                #     quantity = Quantity.from_dict(value)
                #     yield key, quantity
                #     continue
                if "display" in value and "value" in value:  # 'unit' is optional
                    yield (self.level, key), value["display"]
                    continue
                self.level += 1
                for inner_key, inner_value in self.iterate(nested_dict=value):
                    yield inner_key, inner_value
                self.level -= 1
            else:
                yield (self.level, key), value

    # insertion mechanism from https://gist.github.com/jaredks/6276032
    def __insertion(self, link_prev, key_value):
        key, value = key_value
        if link_prev[2] != key:
            if key in self:
                del self[key]
            link_next = link_prev[1]
            self._OrderedDict__map[key] = link_prev[1] = link_next[0] = [
                link_prev,
                link_next,
                key,
            ]
        dict.__setitem__(self, key, value)

    def insert_after(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key], key_value)

    def insert_before(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key][0], key_value)

    def insert_default_plot_options(self, pd_obj, k, update_plot_options=None):
        # make default plot (add entry in 'plots') for each
        # table, first column as x-column
        table_name = "".join([replacements.get(c, c) for c in k])
        key = "default_{}".format(table_name)
        plots_dict = _OrderedDict(
            [
                (
                    mp_level01_titles[2],
                    _OrderedDict(
                        [
                            (
                                key,
                                _OrderedDict(
                                    [("x", pd_obj.columns[0]), ("table", table_name)]
                                ),
                            )
                        ]
                    ),
                )
            ]
        )
        if update_plot_options is not None:
            plots_dict[mp_level01_titles[2]][key].update(update_plot_options)
        if mp_level01_titles[2] in self:
            self.rec_update(plots_dict)
        else:
            self[mp_level01_titles[2]] = plots_dict[mp_level01_titles[2]]

    def render(self):
        """use JsonHuman library to render a dictionary"""
        jdata = json.dumps(self).replace("\\n", " ")
        m = hashlib.md5()
        m.update(jdata.encode("utf-8"))
        divid = m.hexdigest()
        html = f'<div id="{divid}" style="width:100%;"></div><script>'
        html += f'render_json({{divid: "{divid}", data: {jdata}}});</script>'
        return html

    def _ipython_display_(self):
        # TODO jupyterlab mimetype extension
        from IPython.display import display_html

        display_html(self.render(), raw=True)
