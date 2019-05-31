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

#### Entry

```python
# get info about specific project/dataset
client.projects.get_entry(project='dtu')

# use mask to control which fields to retrieve
client.projects.get_entry(project='dtu', mask=['description'])
```

#### Table


#### Graph

## Contributions

## Tables

## Structures
