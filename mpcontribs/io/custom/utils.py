from __future__ import unicode_literals, print_function
import six
from mpcontribs.config import indent_symbol, min_separator_length

def make_pair(key, value, sep=':'):
    """make a mp-specific key-value pair"""
    if not isinstance(value, six.string_types): value = str(value)
    return '{} '.format(sep).join([key, value])

def get_indentor(n=0):
    """get level-n indentor"""
    return indent_symbol * (min_separator_length + n)
