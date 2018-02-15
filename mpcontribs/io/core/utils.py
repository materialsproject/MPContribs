from __future__ import unicode_literals
import warnings, pandas, numpy, six, collections, string
from StringIO import StringIO
from decimal import Decimal
from mpcontribs.config import mp_level01_titles, mp_id_pattern, csv_comment_char

def flatten_dict(dd, separator='.', prefix=''):
    """http://stackoverflow.com/a/19647596"""
    return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_dict(vv, separator, kk).items()
           } if isinstance(dd, dict) else { prefix : dd }

def unflatten_dict(d):
    for k in d:
        value, keys = d.pop(k), k.split('.')
        d.rec_update(nest_dict({keys[-1]: value}, keys[:-1]))

def get_short_object_id(cid):
    length = 7
    cid_short = str(cid)[-length:]
    if cid_short == '0'*length:
        cid_short = str(cid)[:length]
    return cid_short

def make_pair(key, value, sep=':'):
    """make a key-value pair"""
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

def get_composition_from_string(s):
    from pymatgen import Composition, Element
    comp = Composition(s)
    for element in comp.elements:
        Element(element)
    c = comp.get_integer_formula_and_factor()[0]
    comp = Composition(c)
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
    except:
        if mp_id_pattern.match(title.lower()):
            return False, title.lower()
        else:
            return True, title

def clean_value(value, unit='', convert_to_percent=False, max_dgts=3):
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
    v = '{{:.{}g}}'.format(dgts).format(value)
    if unit:
        v += ' {}'.format(unit)
    return v

def strip_converter(text):
    """http://stackoverflow.com/questions/13385860"""
    try:
        text = text.strip()
        if not text:
            return numpy.nan
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
    if not body: return None
    from mpcontribs.io.core.components import Table
    if is_data_section:
        cur_line = 1
        while 1:
            body_split = body.split('\n', cur_line)
            first_line = body_split[cur_line-1].strip()
            cur_line += 1
            if first_line and not first_line.startswith(csv_comment_char):
                break
        options = {'sep': ',', 'header': 0}
        header = map(string.strip, first_line.split(options['sep']))
        body = '\n'.join([options['sep'].join(header), body_split[1]])
        if first_line.startswith('level_'):
            options.update({'index_col': [0, 1]})
        ncols = len(header)
    else:
        options = { 'sep': ':', 'header': None, 'index_col': 0 }
        ncols = 2
    options.update(**kwargs)
    converters = dict((col, strip_converter) for col in range(ncols))
    return Table(pandas.read_csv(
        StringIO(body), comment=csv_comment_char,
        skipinitialspace=True, squeeze=True,
        converters=converters, encoding='utf8',
        **options
    ).dropna(how='all'))

def disable_ipython_scrollbar():
    pass
    #from IPython.display import display, Javascript
    #display(Javascript("""
    #    require("notebook/js/outputarea").OutputArea.prototype._should_scroll=function(){return false;};
    #"""))

def nested_dict_iter(nested, scope=''):
    for key, value in nested.iteritems():
        if isinstance(value, collections.Mapping):
            s = '.'.join([scope, key]) if scope else key
            for inner_key, inner_value in nested_dict_iter(value, scope=s):
                yield '.'.join([s, inner_key]), inner_value
        else:
            yield key, value
