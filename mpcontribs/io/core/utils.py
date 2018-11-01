# -*- coding: utf-8 -*-
"""module defines utility methods for MPContribs core.io library"""
from __future__ import unicode_literals
import warnings
import pandas
import six
import collections
import string
from StringIO import StringIO
from decimal import Decimal
from mpcontribs.config import mp_level01_titles
from mpcontribs.config import mp_id_pattern
from mpcontribs.config import csv_comment_char

def get_short_object_id(cid):
    """return shortened contribution ID (ObjectId) for `cid`.

    >>> get_short_object_id('5a8638add4f144413451852a')
    '451852a'
    >>> get_short_object_id('5a8638add4f1400000000000')
    '5a8638a'
    """
    length = 7
    cid_short = str(cid)[-length:]
    if cid_short == '0'*length:
        cid_short = str(cid)[:length]
    return cid_short

def make_pair(key, value, sep=':'):
    """return string for `key`-`value` pair with separator `sep`.

    >>> make_pair('Phase', 'Hollandite')
    u'Phase: Hollandite'
    >>> print make_pair('ΔH', '0.066 eV/mol', sep=';')
    ΔH; 0.066 eV/mol
    >>> make_pair('k', 2.3)
    u'k: 2.3'
    """
    if not isinstance(value, six.string_types):
        value = unicode(value)
    return '{} '.format(sep).join([key, value])

def nest_dict(dct, keys):
    """nest dict under list of keys"""
    from mpcontribs.io.core.recdict import RecursiveDict
    nested_dict = dct
    for key in reversed(keys):
        nested_dict = RecursiveDict({key: nested_dict})
    return nested_dict

def get_composition_from_string(comp_str):
    """validate and return composition from string `comp_str`."""
    from pymatgen import Composition, Element
    comp = Composition(comp_str)
    for element in comp.elements:
        Element(element)
    formula = comp.get_integer_formula_and_factor()[0]
    comp = Composition(formula)
    return ''.join([
        '{}{}'.format(key, int(value) if value > 1 else '')
        for key, value in comp.as_dict().items()
    ])

def normalize_root_level(title):
    """convert root-level title into conventional identifier; non-identifiers
    become part of shared (meta-)data. Returns: (is_general, title)"""
    try:
        composition = get_composition_from_string(title)
        return False, composition
    except Exception:
        if mp_id_pattern.match(title.lower()):
            return False, title.lower()
        return True, title

def clean_value(value, unit='', convert_to_percent=False, max_dgts=3):
    """return clean value with maximum digits and optional unit and percent"""
    dgts = max_dgts
    value = str(value) if not isinstance(value, six.string_types) else value
    try:
        value = Decimal(value)
        dgts = len(value.as_tuple().digits)
        dgts = max_dgts if dgts > max_dgts else dgts
    except:
        return value
    if convert_to_percent:
        value = Decimal(value) * Decimal('100')
        unit = '%'
    val = '{{:.{}g}}'.format(dgts).format(value)
    if unit:
        val += ' {}'.format(unit)
    return val

def strip_converter(text):
    """http://stackoverflow.com/questions/13385860"""
    try:
        text = text.strip()
        if not text:
            return ''
        try:
            val = clean_value(text, max_dgts=6)
            return str(Decimal(val))
        except:
            return text
    except AttributeError:
        return text

def read_csv(body, is_data_section=True, **kwargs):
    """run pandas.read_csv on (sub)section body"""
    body = body.strip()
    if not body:
        return None
    from mpcontribs.io.core.components import Table
    if is_data_section:
        cur_line = 1
        while 1:
            body_split = body.split('\n', cur_line)
            first_line = body_split[cur_line-1].strip()
            cur_line += 1
            if first_line and not first_line.startswith(csv_comment_char):
                break
        sep = kwargs.get('sep', ',')
        options = {'sep': sep, 'header': 0}
        header = map(string.strip, first_line.split(sep))
        body = '\n'.join([sep.join(header), body_split[1]])
        if first_line.startswith('level_'):
            options.update({'index_col': [0, 1]})
        ncols = len(header)
    else:
        options = {'sep': ':', 'header': None, 'index_col': 0}
        ncols = 2
    options.update(**kwargs)
    converters = dict((col, strip_converter) for col in range(ncols))
    return Table(pandas.read_csv(
        StringIO(body), comment=csv_comment_char,
        skipinitialspace=True, squeeze=True,
        converters=converters, encoding='utf8',
        **options
    ).dropna(how='all'))

def nested_dict_iter(nested, scope=''):
    for key, value in nested.iteritems():
        if isinstance(value, collections.Mapping):
            s = '.'.join([scope, key]) if scope else key
            for inner_key, inner_value in nested_dict_iter(value, scope=s):
                yield '.'.join([s, inner_key]), inner_value
        else:
            yield key, value
