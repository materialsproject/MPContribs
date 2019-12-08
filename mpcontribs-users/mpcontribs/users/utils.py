import inspect, os
from typing import Any, Dict

def get_user_explorer_name(path, view='index'):
    return '_'.join(
        os.path.dirname(os.path.normpath(path)).split(os.sep)[-4:] + [view]
    )

def duplicate_check(f):
    existing_identifiers = {}

    def wrapper(*args, **kwargs):

        module = inspect.getmodule(f)
        module_split = module.__name__.split('.')[:-1]
        mod_path = os.sep.join(module_split)
        from mpcontribs.users_modules import get_user_rester
        Rester = get_user_rester(mod_path)

        test_site = kwargs.get('test_site', True)
        with Rester(test_site=test_site) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.query):
                existing_identifiers[doc['identifier']] = doc['_id']

        try:
            f(*args, **kwargs)
        except StopIteration:
            print('not adding more contributions')

        mpfile = args[0]
        update = 0
        for identifier in mpfile.ids:
            if identifier in existing_identifiers:
                cid = existing_identifiers[identifier]
                mpfile.insert_top(identifier, 'cid', cid)
                update += 1

        print(len(mpfile.ids), 'contributions to submit.')
        if update > 0:
            print(update, 'contributions to update.')

    wrapper.existing_identifiers = existing_identifiers
    return wrapper

# https://stackoverflow.com/a/55545369
def unflatten(
    d: Dict[str, Any],
    base: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Convert any keys containing dotted paths to nested dicts

    >>> unflatten({'a': 12, 'b': 13, 'c': 14})  # no expansion
    {'a': 12, 'b': 13, 'c': 14}

    >>> unflatten({'a.b.c': 12})  # dotted path expansion
    {'a': {'b': {'c': 12}}}

    >>> unflatten({'a.b.c': 12, 'a': {'b.d': 13}})  # merging
    {'a': {'b': {'c': 12, 'd': 13}}}

    >>> unflatten({'a.b': 12, 'a': {'b': 13}})  # insertion-order overwrites
    {'a': {'b': 13}}

    >>> unflatten({'a': {}})  # insertion-order overwrites
    {'a': {}}
    """
    if base is None:
        base = {}

    for key, value in d.items():
        root = base

        ###
        # If a dotted path is encountered, create nested dicts for all but
        # the last level, then change root to that last level, and key to
        # the final key in the path. This allows one final setitem at the bottom
        # of the loop.
        if '.' in key:
            *parts, key = key.split('.')

            for part in parts:
                root.setdefault(part, {})
                root = root[part]

        if isinstance(value, dict):
            value = unflatten(value, root.get(key, {}))

        root[key] = value

    return base
