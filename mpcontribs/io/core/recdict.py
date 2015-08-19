from __future__ import unicode_literals, print_function
import pandas
from collections import OrderedDict as _OrderedDict
from collections import Mapping as _Mapping

class RecursiveDict(_OrderedDict):
    """extension of dict for internal representation of MPFile"""

    def rec_update(self, other, overwrite=False):
        """https://gist.github.com/Xjs/114831"""
        # overwrite=False: don't overwrite existing unnested key
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value)
            elif (key in self and overwrite) or key not in self:
                self[key] = value

    def iterate(self, nested_dict=None):
        """http://stackoverflow.com/questions/10756427/loop-through-all-nested-dictionary-values"""
        d = self if nested_dict is None else nested_dict
        if nested_dict is None: self.level = 0
        self.items = []
        for key,value in d.iteritems():
            if isinstance(value, _Mapping):
                # FIXME: currently skipping all plots sections in output
                #if self.level == 1 and key == mp_level01_titles[2]: continue
                yield get_indentor(n=self.level), key
                self.level += 1
                iterator = self.iterate(nested_dict=value)
                while True:
                    try:
                        inner_key, inner_value = iterator.next()
                    except StopIteration:
                        if self.level > 1 and len(self.items) > 0:
                            yield None, pandas.DataFrame.from_items(self.items)
                        break
                    yield inner_key, inner_value
                self.level -= 1
            elif isinstance(value, list):
                self.items.append((key, value))
            else:
                yield key, value

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
