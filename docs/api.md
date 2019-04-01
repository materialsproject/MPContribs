
# Programmatically retrieve MPContribs Data

Use [bravado](https://bravado.readthedocs.io) as python client
(see [API Docs](https://api.mpcontribs.org) for details about available operations):

## Setup

```python
from bravado.requests_client import RequestsClient
from bravado.client import SwaggerClient

host = 'api.mpcontribs.org'
http_client = RequestsClient()
http_client.set_api_key(
  host, '<YOUR-MAPI-KEY>',
  param_in='header', param_name='x-api-key'
)
apispec = 'https://{}/apispec.json'.format(host)
client = SwaggerClient.from_url(apispec, http_client=http_client,
                               config={'validate_responses': False})

dir(client) # available resources
dir(client.projects) # operations available on resource
```

## Projects

```python
# retrieve list of all available projects/datasets
resp = client.projects.get_entries().response()
projects = [r.project for r in resp.result] # or r.title
print(projects)

# search projects for keywords
resp = client.projects.get_entries(search='bandgap values').response()
projects = [r.project for r in resp.result]
print(projects)

# use mask to control which fields to retrieve
resp = client.projects.get_entries(mask=['project', 'authors']).response()
print(resp.result[0]['authors'])

# get info about specific project/dataset
resp = client.projects.get_entry(project='dtu').response()
print(resp.result.authors)
```
