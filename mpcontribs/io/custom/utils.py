from __future__ import unicode_literals, print_function
import sys, warnings
from six import string_types
from collections import OrderedDict as _OrderedDict
from collections import Mapping as _Mapping
from mpcontribs.config import indent_symbol, min_separator_length, mp_level01_titles
import pandas as pd
import numpy as np

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
                            yield None, pd.DataFrame.from_items(self.items)
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


def nest_dict(dct, keys):
    """nest dict under list of keys"""
    nested_dict = dct
    for key in reversed(keys):
        nested_dict = {key: nested_dict}
    return nested_dict

def force_encoded_string_output(func):
    """http://stackoverflow.com/questions/3627793"""
    if sys.version_info.major < 3:
        def _func(*args, **kwargs):
            return func(*args, **kwargs).encode(sys.stdout.encoding or 'utf-8')
        return _func
    else:
        return func

def make_pair(key, value, sep=':'):
    """make a mp-specific key-value pair"""
    if not isinstance(value, string_types): value = str(value)
    return '{} '.format(sep).join([key, value])

def get_indentor(n=0):
    """get level-n indentor"""
    return indent_symbol * (min_separator_length + n)

def pandas_to_dict(pandas_object):
    """convert pandas object to dict"""
    if pandas_object is None: return RecursiveDict()
    if isinstance(pandas_object, pd.Series):
        return RecursiveDict((k,v) for k,v in pandas_object.iteritems())
    # the remainder of this function is adapted from Pandas' source to
    # preserve the columns order ('list' mode)
    if not pandas_object.columns.is_unique:
        warnings.warn("DataFrame columns are not unique, some "
                      "columns will be omitted.", UserWarning)
    list_dict = RecursiveDict()
    for k, v in pd.compat.iteritems(pandas_object):
        list_dict[k] = v.tolist()
    return list_dict
