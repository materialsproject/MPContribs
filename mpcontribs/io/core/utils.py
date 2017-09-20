import warnings, pandas, numpy, six, collections
from StringIO import StringIO
from pymatgen import Composition, Element
from mpcontribs.config import mp_level01_titles, mp_id_pattern, csv_comment_char
from recdict import RecursiveDict

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
    if not isinstance(value, six.string_types): value = str(value)
    return '{} '.format(sep).join([key, value])

def pandas_to_dict(pandas_object):
    """convert pandas object to dict"""
    if pandas_object is None: return RecursiveDict()
    if isinstance(pandas_object, pandas.Series):
        return RecursiveDict((k,v) for k,v in pandas_object.iteritems())
    # the remainder of this function is adapted from Pandas' source to
    # preserve the columns order ('list' mode)
    if not pandas_object.columns.is_unique:
        warnings.warn("DataFrame columns are not unique, some "
                      "columns will be omitted.", UserWarning)
    list_dict = RecursiveDict()
    for k, v in pandas.compat.iteritems(pandas_object):
        list_dict[k] = v.tolist()
    return list_dict

def nest_dict(dct, keys):
    """nest dict under list of keys"""
    nested_dict = dct
    for key in reversed(keys):
        nested_dict = RecursiveDict({key: nested_dict})
    return nested_dict

def get_composition_from_string(s):
    comp = Composition(s)
    for element in comp.elements:
        Element(element)
    return comp.formula.replace(' ', '')

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

def strip_converter(text):
    """http://stackoverflow.com/questions/13385860"""
    if not text:
        return numpy.nan
    try:
        return float(text)
    except ValueError:
        try:
            return text.strip()
        except AttributeError:
            return text

def read_csv(body, is_data_section=True):
    """run pandas.read_csv on (sub)section body"""
    if not body: return None
    if is_data_section:
        options = { 'sep': ',', 'header': 0 }
        cur_line = 1
        while 1:
            first_line = body.split('\n', cur_line)[cur_line-1]
            cur_line += 1
            if not first_line.strip().startswith(csv_comment_char):
                break
        ncols = len(first_line.split(options['sep']))
    else:
        options = { 'sep': ':', 'header': None, 'index_col': 0 }
        ncols = 2
    converters = dict((col,strip_converter) for col in range(ncols))
    return pandas.read_csv(
        StringIO(body), comment=csv_comment_char,
        skipinitialspace=True, squeeze=True,
        converters=converters, encoding='utf8',
        **options
    ).dropna(how='all')

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
