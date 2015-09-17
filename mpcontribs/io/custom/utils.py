from __future__ import unicode_literals, print_function
from mpcontribs.config import indent_symbol, min_separator_length

def get_indentor(n=0):
    """get level-n indentor"""
    return indent_symbol * (min_separator_length + n)
