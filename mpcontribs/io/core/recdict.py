from __future__ import unicode_literals, print_function
import uuid, json, six
from collections import OrderedDict as _OrderedDict
from collections import Mapping as _Mapping
from mpcontribs.config import mp_level01_titles
from pymatgen import Structure

def render_dict(dct, webapp=False):
    """use JsonHuman library to render a dictionairy"""
    json_str, uuid_str = json.dumps(dct).replace('\\n', ' '), str(uuid.uuid4())
    html = ["<div id='{}' style='width:100%;'></div>".format(uuid_str)]
    html.append("<script>")
    if webapp:
        html.append("requirejs(['main'], function() {")
    html.append("require(['json.human'], function(JsonHuman) {")
    html.append("'use strict';")
    html.append("var data = JSON.parse('{}');".format(json_str))
    html.append("var node = JsonHuman.format(data);")
    html.append("document.getElementById('{}').appendChild(node);".format(uuid_str))
    html.append("});")
    if webapp:
        html.append("});")
    html.append("</script>")
    return ' '.join(html) # TODO use \n?

class RecursiveDict(_OrderedDict):
    """extension of dict for internal representation of MPFile"""

    def rec_update(self, other=None, overwrite=False, replace_newlines=True):
        """https://gist.github.com/Xjs/114831"""
        # overwrite=False: don't overwrite existing unnested key
        if other is None: # mode to force RecursiveDicts to be used
            other = self
            overwrite = True
        for key,value in other.items():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                # ensure RecursiveDict and update key (w/o underscores)
                self[key] = RecursiveDict(self[key])
                replace_newlines = bool(key != mp_level01_titles[3])
                self[key].rec_update(other=value, overwrite=overwrite, replace_newlines=replace_newlines)
            elif (key in self and overwrite) or key not in self:
                if isinstance(value, six.string_types) and replace_newlines:
                    if not isinstance(value, unicode):
                        value = value.decode('utf-8')
                    self[key] = value.replace('\n', ' ')
                else:
                    self[key] = value

    def iterate(self, nested_dict=None):
        """http://stackoverflow.com/questions/10756427/loop-through-all-nested-dictionary-values"""
        d = self if nested_dict is None else nested_dict
        if nested_dict is None: self.level = 0
        self.table = None
        for key,value in d.iteritems():
            if isinstance(value, _Mapping):
                if '@class' in value and value['@class'] == 'Structure':
                    yield key, Structure.from_dict(value)
                    continue
                yield (self.level, key), None
                self.level += 1
                iterator = self.iterate(nested_dict=value)
                while True:
                    try:
                        inner_key, inner_value = iterator.next()
                    except StopIteration:
                        if self.level > 0 and self.table:
                            yield None, self.table
                            self.table = None
                        break
                    yield inner_key, inner_value
                self.level -= 1
            elif isinstance(value, list):
                if isinstance(value[0], dict):
                    # index (from archieml parser)
                    if self.table is None: self.table = ''
                    for row_dct in value:
                        self.table = '\n'.join([
                            self.table, row_dct['value']
                        ])
                    yield '_'.join([mp_level01_titles[1], key]), self.table
                    self.table = None
                else:
                    if self.table is None:
                        self.table = RecursiveDict()
                    self.table[key] = value # columns
            else:
                yield (self.level, key), value

    # insertion mechanism from https://gist.github.com/jaredks/6276032
    def __insertion(self, link_prev, key_value):
        key, value = key_value
        if link_prev[2] != key:
            if key in self:
                del self[key]
            link_next = link_prev[1]
            self._OrderedDict__map[key] = link_prev[1] = link_next[0] = [link_prev, link_next, key]
        dict.__setitem__(self, key, value)

    def insert_after(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key], key_value)

    def insert_before(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key][0], key_value)

    def insert_default_plot_options(self, pd_obj, k, update_plot_options=None):
        # make default plot (add entry in 'plots') for each
        # table, first column as x-column
        table_name = k[len(mp_level01_titles[1]+'_'):]
        key = 'default_{}'.format(k)
        plots_dict = _OrderedDict([(
            mp_level01_titles[2], _OrderedDict([(
                key, _OrderedDict([
                    ('x', pd_obj.columns[0]), ('table', table_name)
                ])
            )])
        )])
        if update_plot_options is not None:
            plots_dict[mp_level01_titles[2]][key].update(update_plot_options)
        if mp_level01_titles[2] in self:
            self.rec_update(plots_dict)
        else:
          kv = (mp_level01_titles[2], plots_dict[mp_level01_titles[2]])
          self.insert_before(k, kv)

    def _ipython_display_(self):
	from IPython.display import display_html
        display_html(render_dict(self), raw=True)
