Small, dynamic python client library to connect to [MPContribs](https://mpcontribs.org)
APIs based on Yelp's [bravado](https://bravado.readthedocs.io).

```python
from mpcontribs.client import load_client
client = load_client('your-api-key-here')
dir(client) # show available resources
```

By default, the client connects to https://api.mpcontribs.org. The `host` argument or the
`MPCONTRIBS_API_HOST` environment variable can be set to connect to other MPContribs-style
APIs:

```python
client = load_client('your-api-key-here', host='ml.materialsproject.cloud')
```
