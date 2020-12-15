![PyPI](https://img.shields.io/pypi/v/mpcontribs-client?style=flat-square)
![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/pypi/mpcontribs-client?style=flat-square)

Small, dynamic python client library to connect to [MPContribs](https://mpcontribs.org)
APIs based on Yelp's [bravado](https://bravado.readthedocs.io).

```python
from mpcontribs.client import Client
client = Client()
dir(client) # show available resources
```

By default, the client connects to https://contribs-api.materialsproject.org and uses the environment variable
`MPCONTRIBS_API_KEY` to set the API key. The key can alternatively be set explicitly via the
`apikey` argument to the constructor. The `host` argument or the `MPCONTRIBS_API_HOST`
environment variable can be set to connect to other MPContribs-style APIs:

```python
client = Client(host='ml-api.materialsproject.org')
```
