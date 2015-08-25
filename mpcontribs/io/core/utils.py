import warnings, pandas, numpy
from StringIO import StringIO
from mpcontribs.pymatgen_utils.composition import Composition
from mpcontribs.config import mp_level01_titles, mp_id_pattern, csv_comment_char
from recdict import RecursiveDict

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
        nested_dict = {key: nested_dict}
    return nested_dict

def normalize_root_level(title):
    """convert root-level title into conventional identifier; non-identifiers
    become part of shared (meta-)data. Returns: (is_general, title)"""
    try:
        composition = Composition(title).get_integer_formula_and_factor()[0]
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
