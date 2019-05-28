import inspect, os

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
    prov = client.projects.get_entry(project=project).response().result
    for k in ['id', 'project', 'other']:
        prov.pop(k)
    ctx['title'] = prov.pop('title')
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = list(prov['urls'].values())
    data = client.projects.get_table(
        project=project, columns=columns, per_page=3
    ).response().result
    if data['items']:
        columns = list(data['items'][0].keys())
        table = Table(data['items'], columns=columns)
        ctx['table'] = table.render(project=project)
    return ctx
