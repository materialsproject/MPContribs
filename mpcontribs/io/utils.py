from collections import OrderedDict

class RecursiveDict(OrderedDict):
    """https://gist.github.com/Xjs/114831"""
    def rec_update(self, other):
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value)
            elif key not in self: # don't overwrite existing unnested key
                self[key] = value

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
