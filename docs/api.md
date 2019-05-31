# Programmatically retrieve MPContribs Data

The [MPContribs API](https://api.mpcontribs.org) provides programmatic access to
experimental and theoretical data contributed by the MP community. Project information is
retrievable through the [`projects`](#projects) resource, and the corresponding
contributed data through the [`contributions`](#contributions) resource. Each project can
contain many contributions for an MP material or composition. Each contribution in turn
consists of three (optional) components: free-form hierarchical data, tabular data, and
crystal structures. There are separate dedicated resource endpoints for
[`tables`](#tables) and [`structures`](#structures) both of which are referenced in the
contributions.

To get started, install the python client library
[mpcontribs-client](https://pypi.org/project/mpcontribs-client/) for the MPContribs API:

```
pip install mpcontribs-client
```

Then get your API key from the [MPContribs
Dashboard](https://portal.mpcontribs.org/dashboard) and set up the client:

```python
from mpcontribs.client import load_client
client = load_client("your-api-key-here")
dir(client) # show available resources
```

Check out the [API Docs](https://api.mpcontribs.org) for more details about the available
resources and operations shown below. The docs can also be used to try out the API in the
browser.

!!! note
    Only the [operation methods](https://bravado.readthedocs.io/en/stable/requests_and_responses.html)
    are shown in the following sections. You can make the actual request and access the
    response via `response()` and `result`, respectively:

    ```python
    operation = client.projects.get_entries()
    resp = operation.response() # make blocking http request
    print(resp.result) # access the API response (result of the request)
    ```

## Projects

### Fields

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| project     | short URL-compatible name                                  |
| title       | short title to fit on contribution cards                   |
| authors     | comma-separated list of authors                            |
| description | paragraph to describe project/dataset                      |
| urls        | list of references in form of URLs                         |
| other       | optional free-form content applicable to all contributions |

### Operations

#### Entries

```python
# retrieve list of all available projects/datasets
client.projects.get_entries()

# search projects for keywords
client.projects.get_entries(search='bandgap values')

# use mask to control which fields to retrieve
client.projects.get_entries(mask=['project', 'authors'])
```

!!! example "Example Response"
    ```python
    [{
        'project': 'dtu',
        'title': 'GLLB-SC Bandgaps',
        'authors': 'I. Castelli, F. Hueser, M. Pandey, H. Li, K. Thygesen, B. Seger',
        'description': 'Bandgaps calculated using GLLB-SC potential ...',
        'urls': {
            'main': 'https://doi.org/10.1002/aenm.201400915',
            'PRA': 'https://doi.org/10.1103/PhysRevA.51.1944',
            'PRB': 'https://doi.org/10.1103/PhysRevB.82.115106'
        },
        'id': '5cdb2591f72fc8ea319bc76f',
        'other': None
    }, ...]
    ```

#### Entry

```python
# get info about specific project/dataset
client.projects.get_entry(project='dtu')

# use mask to control which fields to retrieve
client.projects.get_entry(project='dtu', mask=['description'])
```

!!! example "Example Response"
    ```python
    {
        'title': 'GLLB-SC Bandgaps',
        'authors': 'I. Castelli, F. Hueser, M. Pandey, H. Li, K. Thygesen, B. Seger',
        'description': 'Bandgaps calculated using GLLB-SC potential ...',
        'urls': {
            'main': 'https://doi.org/10.1002/aenm.201400915',
            'PRA': 'https://doi.org/10.1103/PhysRevA.51.1944',
            'PRB': 'https://doi.org/10.1103/PhysRevB.82.115106'
        },
        'id': '5cdb2591f72fc8ea319bc76f'
    }
    ```


#### Table

```python
# retrieve a paginated table of contributions for a project
# - unit will automatically be added to column name
# - columns with URLs to Material and Contribution Detail Pages always included
# - will also include formula column if present in contribution
client.projects.get_table(project='dtu')

# set columns to include in table (use dot notation for nested fields)
client.projects.get_table(project='dtu', columns=['ICSD', 'ΔE-QP.indirect'])

# change number of rows returned per page and retrieve a specific page
client.projects.get_table(project='dtu', per_page=5, page=10)

# search sub-string in formula or identifier (`mp-id`/composition)
client.projects.get_table(project='dtu', q='Cu3')
client.projects.get_table(project='dtu', q='mp-27')

# set field to sort by and its order
client.projects.get_table(project='dtu', sort_by='ΔE-QP.indirect', order='asc')
```

!!! example "Example Response"
    ```python
    {
        'total_count': 10,
        'total_pages': 6,
        'page': 1,
        'last_page': 6,
        'per_page': 2,
        'items': [{
            'identifier': 'https://materialsproject.org/materials/mp-553303',
            'id': 'https://portal.mpcontribs.org/explorer/5abd8f77d4f144494f2cecbb',
            'formula': 'CsCu3O2',
            'ICSD': '413342',
            'ΔE-QP.indirect [eV]': '3.04'
        }, {
            'identifier': 'https://materialsproject.org/materials/mp-7439',
            'id': 'https://portal.mpcontribs.org/explorer/5abd8f78d4f144494f2cecc1',
            'formula': 'Cu3K3P2',
            'ICSD': '12163',
            'ΔE-QP.indirect [eV]': '3.11'
        }, ...]}
    ```

#### Graph

```python
# retrieve overview graph for a project
client.projects.get_graph(project="dtu", columns=['C', 'ΔE-QP.indirect', 'ΔE-QP.direct'])
```

!!! example "Example Response"
    ```python
    [{
        'x': ['mp-1000', 'mp-10086', ...],
        'y': ['1.18', '0.856', ...],
        'text': ['5abd8f7bd4f144494f2cece2', '5abd901ad4f144494f2cf2f3', ...]
    }, {
        'x': ['mp-1000', 'mp-10086', ...],
        'y': ['3.37', '2.97', ...],
        'text': ['5abd8f7bd4f144494f2cece2', '5abd901ad4f144494f2cf2f3', ...]
    }, {
        'x': ['mp-1000', 'mp-10086', ...],
        'y': ['3.71', '2.97', ...],
        'text': ['5abd8f7bd4f144494f2cece2', '5abd901ad4f144494f2cf2f3', ...]
    }]
    ```

## Contributions

## Tables

## Structures
