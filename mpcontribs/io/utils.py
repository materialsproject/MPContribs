from collections import OrderedDict, Mapping
from ..config import indent_symbol, min_indent_level
import pandas as pd
import numpy as np

class RecursiveDict(OrderedDict):
    """extension of dict for internal representation of MPFile"""

    def rec_update(self, other):
        """https://gist.github.com/Xjs/114831"""
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value)
            elif key not in self: # don't overwrite existing unnested key
                self[key] = value

    def iterate(self, nested_dict=None):
        """http://stackoverflow.com/questions/10756427/loop-through-all-nested-dictionary-values"""
        d = self if nested_dict is None else nested_dict
        if nested_dict is None: self.level = 0
        self.items = []
        for key,value in d.iteritems():
            if isinstance(value, Mapping):
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

def nest_dict(dct, keys):
    """nest dict under list of keys"""
    nested_dict = dct
    for key in reversed(keys):
        nested_dict = {key: nested_dict}
    return nested_dict

def make_pair(key, value, sep=':'):
    """make a mp-specific key-value pair"""
    return '{} '.format(sep).join([key, str(value)])

def get_indentor(n=0):
    """get level-n indentor"""
    return indent_symbol * (min_indent_level + n)

def pandas_to_dict(pandas_object):
    """convert pandas object to dict"""
    if pandas_object is None: return RecursiveDict()
    if isinstance(pandas_object, pd.Series):
        return RecursiveDict((k,v) for k,v in pandas_object.iteritems())
    all_columns_numeric = True
    for col in pandas_object.columns:
        if ( pandas_object[col].dtype != np.float64 and \
            pandas_object[col].dtype != np.int64 ):
            all_columns_numeric = False
            break
    return pandas_object.to_dict(
        orient = 'list' if all_columns_numeric else 'records'
    )
