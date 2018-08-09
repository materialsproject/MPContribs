from __future__ import unicode_literals, print_function
import uuid, json, six, os
from collections import OrderedDict as _OrderedDict
from collections import Mapping as _Mapping
from mpcontribs.config import mp_level01_titles, replacements

cwd = os.path.dirname(__file__)
json_human = {}
for ext in ['js', 'css']:
    path_list = [cwd, '..', '..', 'webui', 'static', ext]
    if ext == 'js':
        path_list.append('lib')
    path_list.append('json.human.{}'.format(ext))
    json_human_path = os.path.abspath(os.path.join(*path_list))
    json_human[ext] = open(json_human_path, 'r').read()
json_human['css'] = ' '.join(json_human['css'].replace('\n', ' ').split())

linkify = ''
for lib in ['linkify.min', 'linkify-element.min']:
    path_list = [cwd, '..', '..', 'webui', 'static', 'js', 'lib', '{}.js'.format(lib)]
    lib_path = os.path.abspath(os.path.join(*path_list))
    linkify += open(lib_path, 'r').read().decode("UTF-8")

def render_dict(dct, webapp=False, require=True, script_only=False):
    """use JsonHuman library to render a dictionary"""
    json_str, uuid_str = json.dumps(dct).replace('\\n', ' '), str(uuid.uuid4())
    html = []
    if not script_only:
        html.append("<div id='{}' style='width:100%;'></div>".format(uuid_str))
        html.append("<script>")
    if webapp:
        html.append("requirejs(['main'], function() {")
    if require:
        html.append("require(['json.human', 'linkify-element'], function(JsonHuman, linkifyElement) {")
    else:
        html.append("""
        var style = document.createElement('style');
        style.type = 'text/css';
        var tn = document.createTextNode('{}');
        style.appendChild(tn);
        document.body.appendChild(style);
        """.format(json_human['css']))
        html.append('\n' + json_human['js'])
        html.append('\n' + linkify)
    html.append("'use strict';")
    html.append("var data = JSON.parse('{}');".format(json_str))
    html.append("var node = JsonHuman.format(data);")
    html.append("linkifyElement(node, { target: '_blank' });")
    if script_only:
        html.append("document.body.appendChild(node);")
    else:
        html.append("document.getElementById('{}').appendChild(node);".format(uuid_str))
    if require:
        html.append("});")
    if webapp:
        html.append("});")
    if not script_only:
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
            if isinstance(key, six.string_types):
                key = ''.join([replacements.get(c, c) for c in key])
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
        from mpcontribs.io.core.components import Table
        d = self if nested_dict is None else nested_dict
        if nested_dict is None:
            self.level = 0
        for key in list(d.keys()):
            value = d[key]
            if isinstance(value, _Mapping):
                if value.get('@class') == 'Structure':
                    from pymatgen import Structure
                    yield key, Structure.from_dict(value)
                    continue
                yield (self.level, key), None
                if value.get('@class') == 'Table':
                    yield key, Table.from_dict(value)
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
            self._OrderedDict__map[key] = link_prev[1] = link_next[0] = [link_prev, link_next, key]
        dict.__setitem__(self, key, value)

    def insert_after(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key], key_value)

    def insert_before(self, existing_key, key_value):
        self.__insertion(self._OrderedDict__map[existing_key][0], key_value)

    def insert_default_plot_options(self, pd_obj, k, update_plot_options=None):
        # make default plot (add entry in 'plots') for each
        # table, first column as x-column
        table_name = ''.join([replacements.get(c, c) for c in k])
        key = 'default_{}'.format(table_name)
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
