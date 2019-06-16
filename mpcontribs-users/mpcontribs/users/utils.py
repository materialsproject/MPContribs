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

from mpcontribs.client import load_client
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components.tdata import Table

def get_context(project, columns=None):
    ctx = {'project': project}
    client = load_client()
    mask = ["title", "authors", "description", "urls", "other"]
    prov = client.projects.get_entry(project=project, mask=mask).response().result
    for k in ['id', 'project']:
        prov.pop(k)
    ctx['title'] = prov.pop('title')
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = list(prov['urls'].values())
    if prov['other']:
        ctx['other'] = RecursiveDict(prov['other']).render()
    all_columns = client.projects.get_columns(project=project).response().result
    if columns:
        ncols = len(columns) + 3
        columns += [
            col for col in all_columns
            if col not in columns and col != 'formula'
        ]
    else:
        ncols, columns = 12, list(all_columns)
    data = client.projects.get_table(
        project=project, columns=columns, per_page=3
    ).response().result
    if data['items']:
        columns = list(data['items'][0].keys())
        table = Table(
            data['items'], columns=columns,
            project=project, ncols=ncols
        )
        ctx['table'] = table.render()
    return ctx

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
