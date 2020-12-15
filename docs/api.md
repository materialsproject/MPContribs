**Visit the [apply](https://contribs.materialsproject.org/#apply) and
[work](https://contribs.materialsproject.org/#work) pages on the portal to apply for a project and
get started with the MPContribs API.** The work page provides notebooks with example code
that can be downloaded to execute on your own machine or launched in the browser on remote
compute resources (e.g. https://jupyter.nersc.gov).

The [MPContribs API](https://contribs-api.materialsproject.org) provides programmatic access to
experimental and theoretical data contributed by the MP community. Project information is
retrievable through the [`projects`](#projects) resource, and the corresponding
contributed data through the [`contributions`](#contributions) resource. Each project can
contain many contributions for an MP material or composition. Each contribution in turn
consists of three (optional) components: free-form hierarchical data, tabular data, and
crystal structures. There are separate dedicated resource endpoints for
[`tables`](#tables) and [`structures`](#structures). Descriptions of fields available in
MPContribs resources are shown below.  Check out the [API
Docs](https://contribs-api.materialsproject.org) for more details and to try out the API in the browser.

### Projects

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| name        | short URL-compatible name                                  |
| is_public   | whether the project is publicly available                  |
| title       | short title to fit on contribution cards                   |
| long_title  | long title to show on dataset/project landing page         |
| authors     | comma-separated list of authors                            |
| description | paragraph to describe project/dataset                      |
| references  | list of references in form of dictionaries with `label` and `url` fields |
| other       | optional free-form content applicable to all contributions |
| owner       | owner/submitter of the project                             |
| is_approved | whether the project has been approved by an admin          |
| unique_identifiers | whether identifiers in contributions are unique     |

- the `name` field will also be used in the unique URL to the landing page, i.e.
  `https://contribs.materialsproject.org/<name>`
- If you need to unset/delete a field from `other`, set it to None


### Contributions

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| id                 | unique contribution ID                              |
| project            | identifier for project to which this contribution belongs |
| identifier         | material ID (mp-id) or composition                  |
| is_public          | whether the contribution is publicly available      |
| data               | hierarchical free-form data                         |

- The preferred `data` format is to provide numerical data as strings with units rather than
  naked numerical values. This will be parsed by the API to yield a value and a unit for display.
  This promotes the correct reporting of significant figures as well.
- The data structure that is retrieved by users querying MPContribs will not be identical to
  the one you upload: the API parses things (like string/unit values) and returns the resulting
  data structure
- underscores, spaces, or other punctuation aren’t allowed in `data` field names
- the `id` attribute of a contribution is set automatically
- the `identifier` attribute is user-specified. If project level `unique_identifiers` is `False`,
  duplicate identifiers will cause submission failure
- lists aren’t allowed in contributions
- `data` cannot contain more than 4 levels of nesting
- `NaN` values converted from pandas dataframes cause submission to fail

### Tables

| field      | description                                                |
| ---------- | ---------------------------------------------------------- |
| id                 | unique table ID                              |
| contribution | identifier for contribution to which this table belongs |
| is_public          | whether the table is publicly available      |
| name       | table name (unique together with contribution)     |
| columns    | table header / column names                                |
| data       | table rows (see [Pandas Docs](https://pandas.pydata.org/pandas-docs/version/0.23/generated/pandas.DataFrame.to_dict.html)) |

### Structures

| field      | description                                                |
| ---------- | ---------------------------------------------------------- |
| id                 | unique structure ID                              |
| contribution | identifier for contribution to which this structure belongs |
| is_public          | whether the structure is publicly available      |
| name       | table name (unique together with contribution)     |
| lattice    | pymatgen [lattice](https://github.com/materialsproject/pymatgen/blob/master/pymatgen/core/lattice.py) |
| sites      | list of pymatgen [sites](https://github.com/materialsproject/pymatgen/blob/master/pymatgen/core/sites.py) |
