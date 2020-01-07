!!! bug ""
    **Visit the [application](https://portal.mpcontribs.org/apply) and
    [usage](https://portal.mpcontribs.org/use) pages on the portal to apply for a project and
    get started with the MPContribs API.** The usage page shows notebooks with example code
    that can be copied to execute on your own machine or launched in the browser on MP's
    compute resources.

The [MPContribs API](https://api.mpcontribs.org) provides programmatic access to
experimental and theoretical data contributed by the MP community. Project information is
retrievable through the [`projects`](#projects) resource, and the corresponding
contributed data through the [`contributions`](#contributions) resource. Each project can
contain many contributions for an MP material or composition. Each contribution in turn
consists of three (optional) components: free-form hierarchical data, tabular data, and
crystal structures. There are separate dedicated resource endpoints for
[`tables`](#tables) and [`structures`](#structures). Descriptions of fields available in
MPContribs resources are shown below.  Check out the [API
Docs](https://api.mpcontribs.org) for more details and to try out the API in the browser.

### Projects

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| project     | short URL-compatible name                                  |
| is_public   | whether the project is publicly available                  |
| title       | short title to fit on contribution cards                   |
| authors     | comma-separated list of authors                            |
| description | paragraph to describe project/dataset                      |
| urls        | list of references in form of URLs                         |
| other       | optional free-form content applicable to all contributions |
| owner       | owner/submitter of the project                             |
| is_approved | whether the project has been approved by an admin          |

### Contributions

| field       | description                                                |
| ----------- | ---------------------------------------------------------- |
| id                 | unique contribution ID                              |
| project            | identifier for project to which this contribution belongs |
| identifier         | material ID (mp-id) or composition                  |
| is_public          | whether the contribution is publicly available      |
| data               | hierarchical free-form data                         |

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
