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

!!! tip
    Click the badge below to launch an example notebook in BinderHub and use the
    MPContribs API to retrieve the data you need. You can download the resulting data
    and/or the entire notebook afterwards for use offline. Running the notebook(s) on your
    own machine requires installation of the MPContribs
    [client](https://pypi.org/project/mpcontribs-client/) and
    [I/O](https://pypi.org/project/mpcontribs-io/) libraries. See the [Binder
    Dockerfile](https://github.com/materialsproject/MPContribs/blob/master/binder/Dockerfile)
    for guidance on how to integrate the MPContribs I/O library with Jupyter notebooks.  
    [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/materialsproject/MPContribs/master?filepath=work%2Findex.ipynb)

To get started on your own machine, install the python client library
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
    See [Backbone
    Paginator](https://github.com/backbone-paginator/backbone.paginator#adapting-to-a-server-api)
    for format.


#### Graph

```python
# retrieve overview graph for a project (max. 200 data points per request)
columns = ['C', 'ΔE-QP.indirect', 'ΔE-QP.direct']
client.projects.get_graph(project='dtu', columns=columns)

# change number of data points returned per page and retrieve a specific page
client.projects.get_graph(project='dtu', per_page=5, page=10)

# filter columns and values using a list of `column__operator:value` strings with
# column in dot notation and operator in mongoengine format
filters = ['C__gt:1', 'C__lt:3']
client.projects.get_graph(project='dtu', columns=columns, filters=filters)
```

See [mongoengine docs](http://docs.mongoengine.org/guide/querying.html#query-operators)
for more info about query operators.

!!! example "Example Response"
    The resource will return a dictionary with the `x`, `y`, and `text` keys in the Plotly
    JSON [chart schema](https://help.plot.ly/json-chart-schema/) for each column
    requested. `x` contains the list of identifiers, `y` the values for the requested
    column, and `text` the contribution ID.
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

### Fields

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| id                 | unique contribution ID                              |
| project            | short URL-compatible name                           |
| identifier         | material ID (mp-id) or composition                  |
| collaborators      | list of collaborators/contributors                  |
| content.data       | hierarchical free-form data                         |
| content.tables     | list of references to [tables](#tables)             |
| content.structures | list of references to [structures](#structures)     |

### Operations

#### Entries

```python
# retrieve paginated list of all contributions
client.contributions.get_entries()

# retrieve list of contributions for specific project(s)
client.contributions.get_entries(project=['dtu', 'jarvis_dft'])

# retrieve list of contributions for specific identifiers (mp-id, composition)
client.contributions.get_entries(identifiers=['mp-2715'])

# search for sub-string in identifiers
client.contributions.get_entries(contains='mp-27')

# change number of contributions returned per page and retrieve a specific page
client.contributions.get_entries(per_page=5, page=10)

# use mask to control which fields to retrieve
# - `content.structures` and `content.tables` return references only
mask = ['identifier', 'content.data.C']
client.contributions.get_entries(projects=['dtu'], mask=mask)

# filter fields and values using a list of `field__operator:value` strings with
# field in dot notation, and operator in mongoengine format.
# - filters are implicitly AND
# - only last filter kept for duplicate field/operator combinations
fields = ['<S>', '<σ>', '<S²σ>']
mask = [f'content.data.{field}' for field in fields]
mask += ['content.data.formula', 'identifier']
filters = ['formula__contains:Li3', '<σ>.p__lt:2e15', '<σ>.n__lt:2e15']
client.contributions.get_entries(
    projects=['carrier_transport'], filters=filters, mask=mask
)
```

!!! example "Example Response"
    ```python
    [{
        'id': '5a862202d4f1443a18fab254',
        'project': 'dtu',
        'identifier': 'mp-2715',
        'collaborators': None,
        'content': None
    }, {
        'id': '5a8638a4d4f1444134518527',
        'project': 'MnO2_phase_selection',
        'identifier': 'mp-18767',
        'collaborators': None,
        'content': None
    }
    ```
    See [Entry](#entry_1) documentation for `content` schema.

#### Entry

```python
# retrieve specific contribution with ID `cid`
client.contributions.get_entry(cid='5a8638a4d4f1444134518527')
```

!!! example "Example Response"
    ```python
    {
        'id': '5a8638a4d4f1444134518527',
        'project': 'MnO2_phase_selection',
        'identifier': 'mp-18767',
        'collaborators': [{'email': 'phuck@lbl.gov', 'name': 'Patrick Huck'}],
        'content': {
            'data': {
                'ΔH': {'display': '-3.064 eV/mol', 'value': -3.064, 'unit': 'eV/mol'},
                'formula': 'LiMnO2',
                'phase': 'o-LiMnO2',
                'GS?': 'Yes'
            },
            'structures': ['5cd0ad064fc19150f21ec762'],
            'tables': None
        }
    }
    ```
    See [structures](#structures) and [tables](#tables) resources for their respective
    schema.

#### Card

```python
# retrieve embeddable HTML for contribution card
client.contributions.get_card(cid='5a8638a4d4f1444134518527')
```

??? example "Example Response"
    ```html
    <div name="user_contribs">
        <div class="panel panel-default" style="width: 97%; ...">
            <div class="panel-heading" style="border-bottom: 1px solid transparent; ...">
                <h4 class="panel-title" style="margin-top: 0; ...">
                    <a href="/MnO2_phase_selection">MnO&#8322; Phase Selection</a>
                    <a class="btn-xs btn-default pull-right" role="button"
                       href="/explorer/5a8638a4d4f1444134518527" style="...">
                       Details
                   </a>
                </h4>
            </div>
            <div class="panel-body" style="padding: 15px 15px 15px 0">
                <div style="padding-top: 0px">
                    <div class="well pull-right" style="float: right ! important; ...">
                        <h5 style="margin: 5px;">
                            D. Kitchaev
                            <sup>
                                <a href="https://doi.org/..." target="_blank">1</a>
                            </sup>
                            <a onclick="read_etal_5a8638a4d4f1444134518527()"
                               id="read_etal_5a8638a4d4f1444134518527">et al.</a>
                            <span id="etal_text_5a8638a4d4f1444134518527" hidden>
                                S. Dacek<br>W. Sun<br>G. Ceder<br>
                            </span>
                        </h5>
                    </div>
                    <blockquote class="blockquote" style="font-size: 13px; padding: 0px 10px;">
                        Framework stabilization in MnO&#8322;-derived phases ...
                        <a onclick="read_more_5a8638a4d4f1444134518527()"
                           id="read_more_5a8638a4d4f1444134518527">More &#187;</a>
                        <span id="more_text_5a8638a4d4f1444134518527" hidden>
                            The approach for DFT is SCAN-metaGGA ...
                        </span>
                    </blockquote>
                </div>
                <div class="col-md-12" style="padding-right: 0px;">
                    <table class="jh-type-object jh-root" style="...">
                        <tbody>
                            <tr style="...">
                                <th class="jh-key jh-object-key" style="...">GS?</th>
                                <td class="jh-value jh-object-value" style="...">
                                    <span class="jh-type-string" style="...">Yes</span>
                                </td>
                            </tr>
                            ...
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <script>
            function read_more_5a8638a4d4f1444134518527() {
                document.getElementById("more_text_5a8638a4d4f1444134518527").style.display = "block";
                document.getElementById("read_more_5a8638a4d4f1444134518527").style.display = "none";
            };
            function read_etal_5a8638a4d4f1444134518527() {
                document.getElementById("etal_text_5a8638a4d4f1444134518527").style.display = "block";
                document.getElementById("read_etal_5a8638a4d4f1444134518527").style.display = "none";
            };
        </script>
    </div>
    ```

#### Modal

```python
# retrieve modal data for specific contribution
# - automatically used in pop-up modal on row-click of overview table
client.contributions.get_modal_data(cid='5ac08be3d4f144332ce7b785')
```

!!! example "Example Response"
    ```python
    {'modal': {
        'S': {
            'p': {'ε₁': '722 μV/K', 'ε₂': '783 μV/K', 'ε₃': '806 μV/K'},
            'n': {'ε₁': '-485 μV/K', 'ε₂': '-479 μV/K', 'ε₃': '-477 μV/K'}
        },
        'σ': {
            'p': {'ε₁': '1.37e+15 (Ωms)⁻¹', 'ε₂': '4.83e+15 (Ωms)⁻¹', 'ε₃': '8.09e+15 (Ωms)⁻¹'},
            'n': {'ε₁': '2.16e+16 (Ωms)⁻¹', 'ε₂': '2.60e+16 (Ωms)⁻¹', 'ε₃': '4.84e+16 (Ωms)⁻¹'}
        },
        'mₑᶜᵒⁿᵈ': {
            'p': {'ε₁': '3.48 mₑ', 'ε₂': '5.84 mₑ', 'ε₃': '20.5 mₑ'},
            'n': {'ε₁': '0.582 mₑ', 'ε₂': '1.08 mₑ', 'ε₃': '1.30 mₑ'}
        }
    }}
    ```

## Tables

### Fields

| field      | description                                                |
| ---------- | ---------------------------------------------------------- |
| id         | unique table ID                                            |
| project    | short URL-compatible name                                  |
| identifier | material ID (mp-id) or composition                         |
| name       | table name (unique together with project & identifier)     |
| cid        | contribution ID to which this table belongs                |
| columns    | table header / column names                                |
| data       | table rows (see [Pandas Docs](https://pandas.pydata.org/pandas-docs/version/0.23/generated/pandas.DataFrame.to_dict.html)) |

### Operations

#### Entry

```python
# retrieve a single table in Pandas DataFrame `split` format
tid = '5cca3512e7004456f9b98866'
client.tables.get_entry(tid=tid)

# change number of rows returned per page and retrieve a specific page
client.tables.get_entry(tid=tid, per_page=5, page=2)
```

!!! example "Example Response"
    ```python
    {
        'id': '5cca3512e7004456f9b98866',
        'project': 'carrier_transport',
        'identifier': 'mp-27502',
        'name': 'S(p)',
        'cid': '5ac08be3d4f144332ce7b785',
        'columns': [
            'T [K]', '1e+16 cm⁻³ [μV/K]', '1e+17 cm⁻³ [μV/K]',
            '1e+18 cm⁻³ [μV/K]', '1e+19 cm⁻³ [μV/K]', '1e+20 cm⁻³ [μV/K]'
        ],
        'data': [
            ['100', '966.127', '767.656', '569.354', '372.197', '185.765'],
            ['200', '1080.92', '882.440', '684.078', '486.307', '294.269'],
            ...
        ]
    }
    ```
    See [Pandas
    Docs](https://pandas.pydata.org/pandas-docs/version/0.23/generated/pandas.DataFrame.to_dict.html)
    for more info on `split` format.

#### Backgrid

```python
# retrieve paginated table in backgrid format (items = rows)
cid, name = '5ac08be3d4f144332ce7b785', 'S(p)'
client.tables.get_table(cid=cid, name=name)

# change number of rows returned per page and retrieve a specific page
client.tables.get_table(cid=cid, name=name, per_page=5, page=2)
```

!!! example "Example Response"
	```python
	{
		'total_count': 13,
		'total_pages': 0,
		'page': 1,
		'last_page': 0,
		'per_page': 20,
		'items': [{
			'T [K]': '100',
			'1e+16 cm⁻³ [μV/K]': '966.127',
			'1e+17 cm⁻³ [μV/K]': '767.656', ...
		}, ...]
	}
	```
    See [Backbone
    Paginator](https://github.com/backbone-paginator/backbone.paginator#adapting-to-a-server-api)
    for format.

#### Graph

```python
# retrieve a specific table for a contribution in Plotly format
# - returns x-y-z if number of columns > 2
project, identifier, name = 'carrier_transport', 'mp-27502', 'S(p)'
client.tables.get_graph(project=project, identifier=identifier, name=name)

# change number of rows returned per page and retrieve a specific page
client.tables.get_graph(project=project, identifier=identifier, name=name,
                        per_page=5, page=2)
```

!!! example "Example Response"
    ```python
    {
        'x': ['1e+16', '1e+17', '1e+18', '1e+19', '1e+20'],
        'y': ['100', '200', '300', '400', '500', '600', '700', '800', '900', ...],
        'z': [
            ['966.127', '767.656', '569.354', '372.197', '185.765'],
            ['1080.92', '882.440', '684.078', '486.307', '294.269'], ...
        ]
    }
    ```
    See Plotly JSON [chart schema](https://help.plot.ly/json-chart-schema/).

## Structures

### Fields

| field      | description                                                |
| ---------- | ---------------------------------------------------------- |
| id         | unique structure ID                                        |
| project    | short URL-compatible name                                  |
| identifier | material ID (mp-id) or composition                         |
| name       | structure name (unique together with project & identifier) |
| cid        | contribution ID to which this structure belongs            |
| lattice    | pymatgen [lattice](https://github.com/materialsproject/pymatgen/blob/master/pymatgen/core/lattice.py) |
| sites      | list of pymatgen [sites](https://github.com/materialsproject/pymatgen/blob/master/pymatgen/core/sites.py) |


### Operations

#### Entry

```python
# retrieve single structure with ID `sid`
client.structures.get_entry(sid='5cd0ad074fc19150f21ec775')
```

!!! example "Example Response"
    ```python
    {
        'id': '5cd0ad074fc19150f21ec775',
        'project': 'MnO2_phase_selection',
        'identifier': 'mp-510408',
        'name': 'MnO2',
        'cid': '5a863936d4f1444134518540',
        'lattice': {...},
        'sites': [...]
    }
    ```
    See [Pymatgen
    Code](https://github.com/materialsproject/pymatgen/tree/master/pymatgen/core) for
    format of `lattice` and `sites`.

#### CIF

```python
# retrieve single structure with ID `sid` in CIF format
client.structures.get_cif(sid='5cd0ad074fc19150f21ec775')
```

!!! example "Example Response"
    ```
    # generated using pymatgen
    data_MnO2
    _symmetry_space_group_name_H-M   Pm
    _cell_length_a   4.38523545
    _cell_length_b   2.85605817
    _cell_length_c   4.38543880
    _cell_angle_alpha   90.00000000
    _cell_angle_beta   90.00002504
    _cell_angle_gamma   90.00000000
    _symmetry_Int_Tables_number   6
    _chemical_formula_structural   MnO2
    _chemical_formula_sum   'Mn2 O4'
    _cell_volume   54.92537358
    _cell_formula_units_Z   2
    loop_
     _symmetry_equiv_pos_site_id
     _symmetry_equiv_pos_as_xyz
      1  'x, y, z'
      2  'x, -y, z'
    loop_
     _atom_site_type_symbol
     _atom_site_label
     _atom_site_symmetry_multiplicity
     _atom_site_fract_x
     _atom_site_fract_y
     _atom_site_fract_z
     _atom_site_occupancy
      Mn  Mn1  1  0.000044  0.000000  0.999975  1.0
      Mn  Mn2  1  0.500044  0.500000  0.500025  1.0
      O  O3  1  0.195551  0.500000  0.195482  1.0
      O  O4  1  0.304406  0.000000  0.695493  1.0
      O  O5  1  0.695551  0.000000  0.304518  1.0
      O  O6  1  0.804405  0.500000  0.804506  1.0
    ```
