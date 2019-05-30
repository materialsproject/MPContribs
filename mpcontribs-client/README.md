Small, dynamic python client library to connect to [MPContribs API](https://api.mpcontribs.org) based on Yelp's [bravado](https://bravado.readthedocs.io).

```python
from mpcontribs.client import load_client
api_key = "<replace-me>" # API key from https://portal.mpcontribs.org/dashboard
client = load_client(api_key)
dir(client) # show available resources
```

See the [MPContribs Docs](https://mpcontribs.org/api) for specific usage and examples.
