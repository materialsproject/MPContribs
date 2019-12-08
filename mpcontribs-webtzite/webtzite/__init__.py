from mpcontribs.client import load_client
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components.tdata import Table

def get_client_kwargs(request):
    name = 'X-Consumer-Groups'
    key = f'HTTP_{name.upper().replace("-", "_")}'
    value = request.META.get(key)
    return {'_request_options': {"headers": {name: value}}} if value else {}

def get_context(request, project, columns=None):
    ctx = {'project': project}
    kwargs = get_client_kwargs(request)
    client = load_client()
    mask = ["title", "authors", "description", "urls", "other", "columns"]
    prov = client.projects.get_entry(pk=project, _fields=mask, **kwargs).response().result
    prov.pop('project')
    ctx['title'] = prov.pop('title')
    ctx['descriptions'] = prov['description'].strip().split('.', 1)
    authors = [a.strip() for a in prov['authors'].split(',') if a]
    ctx['authors'] = {'main': authors[0], 'etal': authors[1:]}
    ctx['urls'] = list(prov['urls'].values())
    if prov['other']:
        ctx['other'] = RecursiveDict(prov['other']).render()
    all_columns = prov['columns']
    if not all_columns:
        ctx['table'] = ''
        return ctx
    if columns:
        ncols = len(columns) + 3
        columns += [
            col for col in all_columns
            if col not in columns and col != 'formula'
        ]
    else:
        ncols, columns = 12, list(all_columns)
    data = client.projects.get_table(
        pk=project, columns=columns, per_page=3
    ).response().result
    if data['items']:
        columns = list(data['items'][0].keys())
        table = Table(
            data['items'], columns=columns,
            project=project, ncols=ncols
        )
        ctx['table'] = table.render()
    print(ctx)
    return ctx

