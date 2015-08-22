import warnings, pandas, numpy
from mpcontribs.pymatgen_utils.composition import Composition
from mpcontribs.config import mp_level01_titles, mp_id_pattern
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
    """convert root-level title into conventional identifier format; all
    non-identifiers become part of shared (meta-)data"""
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
